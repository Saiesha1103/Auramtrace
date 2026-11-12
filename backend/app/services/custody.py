"""Custody write operations. Every operation appends MaterialEvent + AuditEvent rows; nothing is overwritten."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, Conflict, NotFound
from ..models import (
    CustodianType,
    JobOrder,
    JobStatus,
    Karigar,
    KarigarStatus,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    User,
)
from ..schemas import AcknowledgeRequest, IssueRequest, LotCreate, ReverseRequest
from . import audit
from .codes import ensure_unique_code, next_code
from .fine_gold import fine_gold, split_weights
from .ledger import VAULT, followups, job_issued_total, lot_balances, karigar_holding


def get_in_org(db: Session, model, organisation_id: uuid.UUID, obj_id: uuid.UUID, label: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.organisation_id != organisation_id:
        raise NotFound(f"{label} not found")
    return obj


def _lock_lot(db: Session, lot_id: uuid.UUID) -> None:
    """Serialise concurrent issues from the same lot (row lock on PostgreSQL; no-op on SQLite)."""
    db.execute(select(MaterialLot.id).where(MaterialLot.id == lot_id).with_for_update())


# --------------------------------------------------------------- lots


def create_lot(db: Session, user: User, req: LotCreate) -> MaterialLot:
    org = user.organisation_id
    if req.source_job_id:
        get_in_org(db, JobOrder, org, req.source_job_id, "Source job")
    code = ensure_unique_code(db, MaterialLot, org, req.code) if req.code else next_code(db, MaterialLot, org, "L")
    stones = split_weights(req.gross_weight_g, req.net_weight_g)
    fine = fine_gold(req.net_weight_g, req.fineness_ppt)
    lot = MaterialLot(
        organisation_id=org,
        code=code,
        metal_type=req.metal_type,
        source=req.source,
        gross_weight_g=req.gross_weight_g,
        net_weight_g=req.net_weight_g,
        stone_weight_g=stones,
        fineness_ppt=req.fineness_ppt,
        fine_gold_g=fine,
        source_job_id=req.source_job_id,
        created_by_id=user.id,
    )
    db.add(lot)
    db.flush()
    ev = MaterialEvent(
        organisation_id=org,
        event_type=MaterialEventType.lot_received,
        lot_id=lot.id,
        job_id=req.source_job_id,
        from_type=CustodianType.external,
        to_type=CustodianType.vault,
        gross_weight_g=req.gross_weight_g,
        net_weight_g=req.net_weight_g,
        fineness_ppt=req.fineness_ppt,
        fine_gold_g=fine,
        scale_id=req.measurement.scale_id,
        operator_name=req.measurement.operator_name,
        measurement_method=req.measurement.method,
        challan_ref=req.challan_ref,
        evidence_ref=req.evidence_ref,
        recorded_by_id=user.id,
        **({"occurred_at": req.occurred_at} if req.occurred_at else {}),
    )
    db.add(ev)
    db.flush()
    audit.record(db, user, org, "lot.created", "material_lot", lot.id, {"code": code, "grossWeightG": req.gross_weight_g, "netWeightG": req.net_weight_g, "finenessPpt": req.fineness_ppt, "fineGoldG": fine, "eventId": ev.id})
    return lot


# --------------------------------------------------------------- issue


def issue(db: Session, user: User, lot: MaterialLot, req: IssueRequest) -> MaterialEvent:
    org = user.organisation_id
    _lock_lot(db, lot.id)
    job = get_in_org(db, JobOrder, org, req.job_id, "Job")
    karigar = get_in_org(db, Karigar, org, req.karigar_id, "Karigar")
    if job.status == JobStatus.cancelled:
        raise BusinessRuleViolation(f"Job {job.code} is cancelled; gold cannot be issued against it", code="job_cancelled")
    if karigar.status != KarigarStatus.active:
        raise BusinessRuleViolation(f"Karigar {karigar.code} is inactive", code="karigar_inactive")
    split_weights(req.gross_weight_g, req.net_weight_g)

    vault = lot_balances(db, lot).get(VAULT)
    avail_net = vault.net if vault else 0
    avail_gross = vault.gross if vault else 0
    if req.net_weight_g > avail_net or req.gross_weight_g > avail_gross:
        raise BusinessRuleViolation(
            f"Lot {lot.code} has only {avail_net:.3f} g net / {avail_gross:.3f} g gross in the vault",
            code="insufficient_balance",
            details={"lotId": str(lot.id), "availableNetWeightG": float(avail_net), "availableGrossWeightG": float(avail_gross), "requestedNetWeightG": float(req.net_weight_g)},
        )

    fine = fine_gold(req.net_weight_g, lot.fineness_ppt)
    ev = MaterialEvent(
        organisation_id=org,
        event_type=MaterialEventType.issue,
        lot_id=lot.id,
        job_id=job.id,
        from_type=CustodianType.vault,
        to_type=CustodianType.karigar,
        to_karigar_id=karigar.id,
        gross_weight_g=req.gross_weight_g,
        net_weight_g=req.net_weight_g,
        fineness_ppt=lot.fineness_ppt,
        fine_gold_g=fine,
        scale_id=req.measurement.scale_id,
        operator_name=req.measurement.operator_name,
        measurement_method=req.measurement.method,
        challan_ref=req.challan_ref,
        evidence_ref=req.evidence_ref,
        note=req.note,
        recorded_by_id=user.id,
        **({"occurred_at": req.occurred_at} if req.occurred_at else {}),
    )
    db.add(ev)
    if job.status == JobStatus.draft:
        job.status = JobStatus.issued
    db.flush()
    audit.record(db, user, org, "material.issued", "material_event", ev.id, {"lot": lot.code, "job": job.code, "karigar": karigar.code, "netWeightG": req.net_weight_g, "fineGoldG": fine, "challanRef": req.challan_ref})
    return ev


# --------------------------------------------------------------- acknowledge


def acknowledge(db: Session, user: User, issue_ev: MaterialEvent, req: AcknowledgeRequest) -> MaterialEvent:
    if issue_ev.event_type != MaterialEventType.issue:
        raise BusinessRuleViolation("Only issue events can be acknowledged", code="not_acknowledgeable")
    fu = followups(db, [issue_ev.id])[issue_ev.id]
    if fu.reversal_id:
        raise BusinessRuleViolation("This issue was reversed and cannot be acknowledged", code="event_reversed")
    if fu.acknowledgement_id:
        raise Conflict("This issue is already acknowledged", code="already_acknowledged")
    ev = MaterialEvent(
        organisation_id=issue_ev.organisation_id,
        event_type=MaterialEventType.issue_acknowledged,
        lot_id=issue_ev.lot_id,
        job_id=issue_ev.job_id,
        to_type=issue_ev.to_type,
        to_karigar_id=issue_ev.to_karigar_id,
        ref_event_id=issue_ev.id,
        acknowledged_by_name=req.acknowledged_by_name,
        evidence_ref=req.evidence_ref,
        note=req.note,
        recorded_by_id=user.id,
        **({"occurred_at": req.occurred_at} if req.occurred_at else {}),
    )
    db.add(ev)
    db.flush()
    audit.record(db, user, issue_ev.organisation_id, "material.issue_acknowledged", "material_event", ev.id, {"issueEventId": issue_ev.id, "acknowledgedByName": req.acknowledged_by_name, "evidenceRef": req.evidence_ref})
    return ev


# --------------------------------------------------------------- reverse


def reverse(db: Session, user: User, original: MaterialEvent, req: ReverseRequest) -> MaterialEvent:
    """Correct an event by appending its mirror image. The original row is never modified."""
    if original.event_type == MaterialEventType.reversal:
        raise BusinessRuleViolation("A reversal cannot itself be reversed; record a new event instead", code="not_reversible")
    fu = followups(db, [original.id])[original.id]
    if fu.reversal_id:
        raise Conflict("This event has already been reversed", code="already_reversed")

    lot = db.get(MaterialLot, original.lot_id)
    _lock_lot(db, lot.id)

    if original.event_type == MaterialEventType.issue:
        if fu.acknowledgement_id and not fu.acknowledgement_reversed:
            raise BusinessRuleViolation(
                "The receiver has acknowledged this issue. Reverse the acknowledgement first, or record a return (later phase).",
                code="acknowledged_issue",
            )
        held = lot_balances(db, lot).get(str(original.to_karigar_id))
        if not held or held.net < original.net_weight_g:
            raise BusinessRuleViolation("The karigar no longer holds this metal from the lot; it cannot be reversed back to the vault", code="insufficient_balance")
    elif original.event_type == MaterialEventType.lot_received:
        vault = lot_balances(db, lot).get(VAULT)
        if not vault or vault.net < original.net_weight_g:
            raise BusinessRuleViolation(f"Lot {lot.code} has metal issued out; reverse those issues before reversing the receipt", code="lot_in_use")

    moves = original.gross_weight_g is not None
    ev = MaterialEvent(
        organisation_id=original.organisation_id,
        event_type=MaterialEventType.reversal,
        lot_id=original.lot_id,
        job_id=original.job_id,
        from_type=original.to_type if moves else None,
        from_karigar_id=original.to_karigar_id if moves else None,
        to_type=original.from_type if moves else None,
        to_karigar_id=original.from_karigar_id if moves else None,
        gross_weight_g=original.gross_weight_g,
        net_weight_g=original.net_weight_g,
        fineness_ppt=original.fineness_ppt,
        fine_gold_g=original.fine_gold_g,
        ref_event_id=original.id,
        note=req.reason,
        recorded_by_id=user.id,
    )
    db.add(ev)
    db.flush()

    if original.event_type == MaterialEventType.issue and original.job_id:
        job = db.get(JobOrder, original.job_id)
        if job.status == JobStatus.issued and job_issued_total(db, job.id).net == 0:
            job.status = JobStatus.draft

    audit.record(db, user, original.organisation_id, "material.reversed", "material_event", ev.id, {"reversedEventId": original.id, "reversedEventType": original.event_type, "reason": req.reason})
    return ev


__all__ = ["create_lot", "issue", "acknowledge", "reverse", "get_in_org", "karigar_holding"]
