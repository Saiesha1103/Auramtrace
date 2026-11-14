"""Material return operations: finished jewellery, scrap, dust, and WIP.

Custody rules:
  * Returns move metal from karigar → vault via append-only MaterialEvent (return_vault).
  * Gross weight, net metal weight, and stone weight remain strictly separated.
  * Stone weight is NEVER counted as gold.
  * Declared fineness and verified assayed fineness are recorded separately.
  * Every return is traceable to the original lot and job.
  * Partial returns keep the job open in WIP; full returns transition to returned status.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    CustodianType,
    JobOrder,
    JobStatus,
    Karigar,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    MaterialReturn,
    ReturnCategory,
    User,
)
from ..models.base import utcnow
from ..schemas import MaterialReturnAssayUpdate, MaterialReturnCreate
from . import audit
from .codes import ensure_unique_code, next_code
from .custody import _lock_lot, get_in_org
from .fine_gold import fine_gold, split_weights
from .ledger import followups, lot_balances


def create_return(db: Session, user: User, req: MaterialReturnCreate) -> MaterialReturn:
    org = user.organisation_id
    lot = get_in_org(db, MaterialLot, org, req.lot_id, "Material lot")
    _lock_lot(db, lot.id)

    job = get_in_org(db, JobOrder, org, req.job_id, "Job")
    karigar = get_in_org(db, Karigar, org, req.karigar_id, "Karigar")

    if job.status == JobStatus.cancelled:
        raise BusinessRuleViolation(f"Job {job.code} is cancelled; cannot return material", code="job_cancelled")

    split_weights(req.gross_weight_g, req.net_metal_weight_g)

    # Balance verification: karigar must hold sufficient net metal from this lot
    held = lot_balances(db, lot).get(str(karigar.id))
    avail_net = held.net if held else Decimal("0.000")
    avail_gross = held.gross if held else Decimal("0.000")
    if req.net_metal_weight_g > avail_net:
        raise BusinessRuleViolation(
            f"Karigar {karigar.code} holds only {avail_net:.3f} g net from lot {lot.code}",
            code="insufficient_balance",
            details={
                "karigarId": str(karigar.id),
                "lotId": str(lot.id),
                "availableNetWeightG": float(avail_net),
                "availableGrossWeightG": float(avail_gross),
                "requestedNetWeightG": float(req.net_metal_weight_g),
            },
        )

    # Fine gold is calculated using verified assayed fineness if available, else declared
    effective_fineness = req.assayed_fineness_ppt if req.assayed_fineness_ppt is not None else req.declared_fineness_ppt
    fine = fine_gold(req.net_metal_weight_g, effective_fineness)

    # 1. Append immutable custody ledger event (karigar → vault)
    ev = MaterialEvent(
        organisation_id=org,
        event_type=MaterialEventType.return_vault,
        lot_id=lot.id,
        job_id=job.id,
        from_type=CustodianType.karigar,
        from_karigar_id=karigar.id,
        to_type=CustodianType.vault,
        to_karigar_id=None,
        gross_weight_g=req.gross_weight_g,
        net_weight_g=req.net_metal_weight_g,
        fineness_ppt=effective_fineness,
        fine_gold_g=fine,
        scale_id=req.measurement.scale_id,
        operator_name=req.measurement.operator_name,
        measurement_method=req.measurement.method,
        challan_ref=req.challan_ref,
        evidence_ref=req.evidence_ref,
        note=req.notes,
        recorded_by_id=user.id,
        **({"occurred_at": req.occurred_at} if req.occurred_at else {}),
    )
    db.add(ev)
    db.flush()

    # 2. Create MaterialReturn record linked to the event
    code = ensure_unique_code(db, MaterialReturn, org, req.code) if req.code else next_code(db, MaterialReturn, org, "RET")
    ret = MaterialReturn(
        organisation_id=org,
        code=code,
        job_id=job.id,
        karigar_id=karigar.id,
        lot_id=lot.id,
        return_category=req.return_category,
        gross_weight_g=req.gross_weight_g,
        net_metal_weight_g=req.net_metal_weight_g,
        stone_weight_g=req.stone_weight_g,
        declared_fineness_ppt=req.declared_fineness_ppt,
        assayed_fineness_ppt=req.assayed_fineness_ppt,
        fine_gold_g=fine,
        pieces=req.pieces,
        is_partial=req.is_partial,
        retained_scrap_g=req.retained_scrap_g,
        scale_id=req.measurement.scale_id,
        operator_name=req.measurement.operator_name,
        measurement_method=req.measurement.method,
        challan_ref=req.challan_ref,
        evidence_ref=req.evidence_ref,
        assay_evidence_ref=req.assay_evidence_ref,
        notes=req.notes,
        material_event_id=ev.id,
        recorded_by_id=user.id,
    )
    db.add(ret)

    # Job lifecycle progression
    if not req.is_partial and job.status in (JobStatus.in_production, JobStatus.issued):
        job.status = JobStatus.returned

    db.flush()
    audit.record(
        db,
        user,
        org,
        "material.returned",
        "material_return",
        ret.id,
        {
            "code": code,
            "jobCode": job.code,
            "karigarCode": karigar.code,
            "category": req.return_category.value,
            "grossWeightG": req.gross_weight_g,
            "netWeightG": req.net_metal_weight_g,
            "fineGoldG": fine,
            "isPartial": req.is_partial,
        },
    )
    return ret


def update_assay_result(db: Session, user: User, ret: MaterialReturn, req: MaterialReturnAssayUpdate) -> MaterialReturn:
    ret.assayed_fineness_ppt = req.assayed_fineness_ppt
    if req.assay_evidence_ref:
        ret.assay_evidence_ref = req.assay_evidence_ref
    if req.notes:
        ret.notes = f"{ret.notes or ''}\nAssay update: {req.notes}".strip()

    # Recalculate fine gold for the return record
    ret.fine_gold_g = fine_gold(ret.net_metal_weight_g, req.assayed_fineness_ppt)
    db.flush()

    audit.record(
        db,
        user,
        ret.organisation_id,
        "material.assay_updated",
        "material_return",
        ret.id,
        {
            "returnCode": ret.code,
            "declaredFinenessPpt": ret.declared_fineness_ppt,
            "assayedFinenessPpt": req.assayed_fineness_ppt,
            "newFineGoldG": ret.fine_gold_g,
        },
    )
    return ret


def list_returns(db: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, karigar_id: uuid.UUID | None = None, category: ReturnCategory | None = None) -> list[MaterialReturn]:
    stmt = select(MaterialReturn).where(MaterialReturn.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(MaterialReturn.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(MaterialReturn.karigar_id == karigar_id)
    if category:
        stmt = stmt.where(MaterialReturn.return_category == category)
    return list(db.scalars(stmt.order_by(MaterialReturn.created_at.desc())))
