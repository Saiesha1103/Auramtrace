"""Material transfers between karigars and job lineage operations.

Custody rules:
  * Transfers move metal karigar → karigar via append-only MaterialEvent rows.
  * Sender must hold sufficient available gross/net metal from the specified lot.
  * Transfers require explicit receiver acknowledgement.
  * Reversals create compensating mirror events; historical rows are never updated or deleted.
  * Concurrent transfers from the same lot are serialized using row locks.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, Conflict, NotFound
from ..models import (
    CustodianType,
    JobOrder,
    JobSplit,
    JobStatus,
    Karigar,
    KarigarKind,
    KarigarStatus,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    User,
)
from ..schemas import (
    CustodyLineageEdge,
    CustodyLineageGraph,
    CustodyLineageNode,
    JobLineageOut,
    JobRef,
    JobSplitOut,
    JobSplitRequest,
    KarigarRef,
    MeasurementOut,
    TransferAcknowledgeRequest,
    TransferCreate,
    TransferOut,
    TransferReverseRequest,
)
from . import audit
from .codes import ensure_unique_code, next_code
from .custody import _lock_lot, get_in_org
from .fine_gold import fine_gold, split_weights
from .ledger import followups, lot_balances


def create_transfer(db: Session, user: User, req: TransferCreate) -> MaterialEvent:
    org = user.organisation_id
    lot = get_in_org(db, MaterialLot, org, req.lot_id, "Material lot")
    _lock_lot(db, lot.id)

    job = get_in_org(db, JobOrder, org, req.job_id, "Job")
    from_k = get_in_org(db, Karigar, org, req.from_karigar_id, "Sender karigar")
    to_k = get_in_org(db, Karigar, org, req.to_karigar_id, "Receiver karigar")

    if job.status == JobStatus.cancelled:
        raise BusinessRuleViolation(f"Job {job.code} is cancelled; cannot transfer metal", code="job_cancelled")
    if from_k.status != KarigarStatus.active:
        raise BusinessRuleViolation(f"Sender karigar {from_k.code} is inactive", code="karigar_inactive")
    if to_k.status != KarigarStatus.active:
        raise BusinessRuleViolation(f"Receiver karigar {to_k.code} is inactive", code="karigar_inactive")
    if from_k.id == to_k.id:
        raise BusinessRuleViolation("Sender and receiver karigar cannot be the same", code="self_transfer")

    split_weights(req.gross_weight_g, req.net_weight_g)

    # Balance check: sender must hold enough metal of this lot
    held = lot_balances(db, lot).get(str(from_k.id))
    avail_net = held.net if held else Decimal("0.000")
    avail_gross = held.gross if held else Decimal("0.000")
    if req.net_weight_g > avail_net or req.gross_weight_g > avail_gross:
        raise BusinessRuleViolation(
            f"Karigar {from_k.code} holds only {avail_net:.3f} g net / {avail_gross:.3f} g gross from lot {lot.code}",
            code="insufficient_balance",
            details={
                "karigarId": str(from_k.id),
                "lotId": str(lot.id),
                "availableNetWeightG": float(avail_net),
                "availableGrossWeightG": float(avail_gross),
                "requestedNetWeightG": float(req.net_weight_g),
            },
        )

    fine = fine_gold(req.net_weight_g, lot.fineness_ppt)
    ev = MaterialEvent(
        organisation_id=org,
        event_type=MaterialEventType.transfer,
        lot_id=lot.id,
        job_id=job.id,
        from_type=CustodianType.karigar,
        from_karigar_id=from_k.id,
        to_type=CustodianType.karigar,
        to_karigar_id=to_k.id,
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

    if job.status in (JobStatus.draft, JobStatus.issued):
        job.status = JobStatus.in_production

    db.flush()
    audit.record(
        db,
        user,
        org,
        "material.transferred",
        "material_event",
        ev.id,
        {
            "lot": lot.code,
            "job": job.code,
            "fromKarigar": from_k.code,
            "toKarigar": to_k.code,
            "netWeightG": req.net_weight_g,
            "fineGoldG": fine,
            "challanRef": req.challan_ref,
        },
    )
    return ev


def acknowledge_transfer(db: Session, user: User, transfer_ev: MaterialEvent, req: TransferAcknowledgeRequest) -> MaterialEvent:
    if transfer_ev.event_type != MaterialEventType.transfer:
        raise BusinessRuleViolation("Only transfer events can be acknowledged via this endpoint", code="not_acknowledgeable")
    fu = followups(db, [transfer_ev.id])[transfer_ev.id]
    if fu.reversal_id:
        raise BusinessRuleViolation("This transfer was reversed and cannot be acknowledged", code="event_reversed")
    if fu.acknowledgement_id and not fu.acknowledgement_reversed:
        raise Conflict("This transfer has already been acknowledged", code="already_acknowledged")

    ev = MaterialEvent(
        organisation_id=transfer_ev.organisation_id,
        event_type=MaterialEventType.transfer_acknowledged,
        lot_id=transfer_ev.lot_id,
        job_id=transfer_ev.job_id,
        from_type=transfer_ev.from_type,
        from_karigar_id=transfer_ev.from_karigar_id,
        to_type=transfer_ev.to_type,
        to_karigar_id=transfer_ev.to_karigar_id,
        ref_event_id=transfer_ev.id,
        acknowledged_by_name=req.acknowledged_by_name,
        evidence_ref=req.evidence_ref,
        note=req.note,
        recorded_by_id=user.id,
        **({"occurred_at": req.occurred_at} if req.occurred_at else {}),
    )
    db.add(ev)
    db.flush()
    audit.record(
        db,
        user,
        transfer_ev.organisation_id,
        "material.transfer_acknowledged",
        "material_event",
        ev.id,
        {"transferEventId": transfer_ev.id, "acknowledgedByName": req.acknowledged_by_name, "evidenceRef": req.evidence_ref},
    )
    return ev


def reverse_transfer(db: Session, user: User, original: MaterialEvent, req: TransferReverseRequest) -> MaterialEvent:
    if original.event_type != MaterialEventType.transfer:
        raise BusinessRuleViolation("Only transfer events can be reversed via this endpoint", code="not_reversible")
    fu = followups(db, [original.id])[original.id]
    if fu.reversal_id:
        raise Conflict("This transfer has already been reversed", code="already_reversed")

    lot = db.get(MaterialLot, original.lot_id)
    _lock_lot(db, lot.id)

    # Receiver must still hold the metal to reverse it back to sender
    held = lot_balances(db, lot).get(str(original.to_karigar_id))
    if not held or held.net < original.net_weight_g:
        raise BusinessRuleViolation(
            "Receiver karigar no longer holds enough metal from this lot; cannot reverse transfer",
            code="insufficient_balance",
        )

    ev = MaterialEvent(
        organisation_id=original.organisation_id,
        event_type=MaterialEventType.reversal,
        lot_id=original.lot_id,
        job_id=original.job_id,
        from_type=original.to_type,
        from_karigar_id=original.to_karigar_id,
        to_type=original.from_type,
        to_karigar_id=original.from_karigar_id,
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
    audit.record(
        db,
        user,
        original.organisation_id,
        "material.transfer_reversed",
        "material_event",
        ev.id,
        {"reversedEventId": original.id, "reason": req.reason},
    )
    return ev


def split_job(db: Session, user: User, parent: JobOrder, req: JobSplitRequest) -> tuple[JobOrder, JobSplit]:
    org = user.organisation_id
    if parent.status == JobStatus.cancelled:
        raise BusinessRuleViolation("Cancelled jobs cannot be split", code="job_cancelled")
    if req.allocated_pieces >= parent.pieces:
        raise BusinessRuleViolation("Allocated split pieces must be strictly less than parent job pieces", code="invalid_split_pieces")

    child_code = ensure_unique_code(db, JobOrder, org, req.child_job_code) if req.child_job_code else next_code(db, JobOrder, org, "J")
    child_title = req.child_title or f"{parent.title} (Split - Part B)"
    child_head_id = req.head_karigar_id or parent.head_karigar_id
    due_date = req.due_date or parent.due_date

    # Deduct pieces from parent job
    parent.pieces -= req.allocated_pieces

    child = JobOrder(
        organisation_id=org,
        code=child_code,
        title=child_title,
        order_ref=parent.order_ref,
        process=parent.process,
        karat=parent.karat,
        target_fineness_ppt=parent.target_fineness_ppt,
        pieces=req.allocated_pieces,
        target_gross_per_piece_g=parent.target_gross_per_piece_g,
        loss_allowance_pct=parent.loss_allowance_pct,
        contract_version=parent.contract_version,
        head_karigar_id=child_head_id,
        parent_job_id=parent.id,
        due_date=due_date,
        notes=f"Split from {parent.code}. Reason: {req.split_reason or 'No reason provided'}",
        status=JobStatus.draft,
        created_by_id=user.id,
    )
    db.add(child)
    db.flush()

    split = JobSplit(
        organisation_id=org,
        parent_job_id=parent.id,
        child_job_id=child.id,
        allocated_pieces=req.allocated_pieces,
        allocated_gross_weight_g=req.allocated_gross_weight_g,
        split_reason=req.split_reason,
        created_by_id=user.id,
    )
    db.add(split)
    db.flush()

    audit.record(
        db,
        user,
        org,
        "job.split",
        "job_order",
        child.id,
        {"parentJobId": parent.id, "parentCode": parent.code, "childCode": child.code, "allocatedPieces": req.allocated_pieces},
    )
    return child, split


def get_job_lineage(db: Session, org_id: uuid.UUID, job: JobOrder) -> JobLineageOut:
    splits_raw = list(
        db.scalars(
            select(JobSplit).where(
                JobSplit.organisation_id == org_id,
                (JobSplit.parent_job_id == job.id) | (JobSplit.child_job_id == job.id),
            )
        )
    )
    splits = [
        JobSplitOut(
            id=s.id,
            parent_job_id=s.parent_job_id,
            child_job_id=s.child_job_id,
            allocated_pieces=s.allocated_pieces,
            allocated_gross_weight_g=s.allocated_gross_weight_g,
            split_reason=s.split_reason,
            created_at=s.created_at,
        )
        for s in splits_raw
    ]

    parent_ref = JobRef(id=job.parent_job.id, code=job.parent_job.code, title=job.parent_job.title, status=job.parent_job.status) if job.parent_job else None
    child_refs = [JobRef(id=c.id, code=c.code, title=c.title, status=c.status) for c in job.child_jobs]

    total_events = len(list(db.scalars(select(MaterialEvent.id).where(MaterialEvent.job_id == job.id))))

    return JobLineageOut(
        job_id=job.id,
        code=job.code,
        title=job.title,
        parent_job=parent_ref,
        child_jobs=child_refs,
        splits=splits,
        total_events=total_events,
    )


def get_custody_lineage_graph(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> CustodyLineageGraph:
    events = list(
        db.scalars(
            select(MaterialEvent)
            .where(MaterialEvent.organisation_id == org_id, MaterialEvent.job_id == job_id)
            .order_by(MaterialEvent.recorded_at)
        )
    )
    nodes_dict: dict[str, CustodyLineageNode] = {}
    edges: list[CustodyLineageEdge] = []

    karigar_ids = {e.from_karigar_id for e in events if e.from_karigar_id} | {e.to_karigar_id for e in events if e.to_karigar_id}
    karigars = {k.id: k for k in db.scalars(select(Karigar).where(Karigar.id.in_(karigar_ids)))} if karigar_ids else {}

    # Initialize vault node
    nodes_dict["vault"] = CustodyLineageNode(
        custodian_type=CustodianType.vault,
        karigar_id=None,
        name="Main Vault",
        kind="vault",
        net_weight_g=Decimal("0.000"),
        fine_gold_g=Decimal("0.000"),
    )

    for k_id, k in karigars.items():
        nodes_dict[str(k_id)] = CustodyLineageNode(
            custodian_type=CustodianType.karigar,
            karigar_id=k.id,
            name=k.name,
            kind=k.kind.value,
            net_weight_g=Decimal("0.000"),
            fine_gold_g=Decimal("0.000"),
        )

    for e in events:
        if e.gross_weight_g is not None and e.net_weight_g is not None:
            src = "vault" if e.from_type == CustodianType.vault else (str(e.from_karigar_id) if e.from_karigar_id else "external")
            dst = "vault" if e.to_type == CustodianType.vault else (str(e.to_karigar_id) if e.to_karigar_id else "external")
            edges.append(
                CustodyLineageEdge(
                    source=src,
                    target=dst,
                    event_id=e.id,
                    event_type=e.event_type.value,
                    gross_weight_g=e.gross_weight_g,
                    net_weight_g=e.net_weight_g,
                    fine_gold_g=e.fine_gold_g or Decimal("0.000"),
                    recorded_at=e.recorded_at,
                )
            )

    return CustodyLineageGraph(job_id=job_id, nodes=list(nodes_dict.values()), edges=edges)
