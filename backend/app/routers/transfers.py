"""Material transfers between karigars."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager, VaultOperator
from ..errors import NotFound
from ..models import (
    Karigar,
    MaterialEvent,
    MaterialEventType,
)
from ..schemas import (
    ERROR_RESPONSES,
    KarigarRef,
    MeasurementOut,
    Page,
    TransferAcknowledgeRequest,
    TransferCreate,
    TransferOut,
    TransferReverseRequest,
)
from ..services.custody import get_in_org
from ..services.ledger import followups
from ..services.transfers import acknowledge_transfer, create_transfer, reverse_transfer

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _to_transfer_out(db: DB, ev: MaterialEvent) -> TransferOut:
    fu = followups(db, [ev.id])[ev.id]
    ack_ev = db.get(MaterialEvent, fu.acknowledgement_id) if fu.acknowledgement_id else None

    from_ref = KarigarRef(
        id=ev.from_karigar.id,
        code=ev.from_karigar.code,
        name=ev.from_karigar.name,
        kind=ev.from_karigar.kind,
    )
    to_ref = KarigarRef(
        id=ev.to_karigar.id,
        code=ev.to_karigar.code,
        name=ev.to_karigar.name,
        kind=ev.to_karigar.kind,
    )

    return TransferOut(
        id=ev.id,
        event_id=ev.id,
        job_id=ev.job_id,
        lot_id=ev.lot_id,
        from_karigar=from_ref,
        to_karigar=to_ref,
        gross_weight_g=ev.gross_weight_g,
        net_weight_g=ev.net_weight_g,
        fineness_ppt=ev.fineness_ppt,
        fine_gold_g=ev.fine_gold_g,
        measurement=MeasurementOut(scale_id=ev.scale_id, operator_name=ev.operator_name, method=ev.measurement_method),
        challan_ref=ev.challan_ref,
        evidence_ref=ev.evidence_ref,
        note=ev.note,
        is_acknowledged=bool(fu.acknowledgement_id and not fu.acknowledgement_reversed),
        acknowledged_by_name=ack_ev.acknowledged_by_name if ack_ev else None,
        acknowledged_at=ack_ev.recorded_at if ack_ev else None,
        is_reversed=bool(fu.reversal_id),
        occurred_at=ev.occurred_at,
        recorded_at=ev.recorded_at,
    )


@router.post("", response_model=TransferOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_transfer(req: TransferCreate, db: DB, user: VaultOperator):
    """Transfer metal between karigars against an active job. Appends an immutable transfer event."""
    ev = create_transfer(db, user, req)
    db.commit()
    return _to_transfer_out(db, ev)


@router.get("", response_model=Page[TransferOut], responses=ERROR_RESPONSES)
def list_transfers(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    from_karigar_id: uuid.UUID | None = Query(None, alias="fromKarigarId"),
    to_karigar_id: uuid.UUID | None = Query(None, alias="toKarigarId"),
    lot_id: uuid.UUID | None = Query(None, alias="lotId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List material transfers scoped to caller's organisation."""
    stmt = (
        select(MaterialEvent)
        .where(
            MaterialEvent.organisation_id == user.organisation_id,
            MaterialEvent.event_type == MaterialEventType.transfer,
        )
    )
    if job_id:
        stmt = stmt.where(MaterialEvent.job_id == job_id)
    if from_karigar_id:
        stmt = stmt.where(MaterialEvent.from_karigar_id == from_karigar_id)
    if to_karigar_id:
        stmt = stmt.where(MaterialEvent.to_karigar_id == to_karigar_id)
    if lot_id:
        stmt = stmt.where(MaterialEvent.lot_id == lot_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(MaterialEvent.recorded_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_transfer_out(db, i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=TransferOut, responses=ERROR_RESPONSES)
def get_transfer(id: uuid.UUID, db: DB, user: CurrentUser):
    ev = get_in_org(db, MaterialEvent, user.organisation_id, id, "Transfer event")
    if ev.event_type != MaterialEventType.transfer:
        raise NotFound("Transfer event not found")
    return _to_transfer_out(db, ev)


@router.post("/{id}/acknowledge", response_model=TransferOut, responses=ERROR_RESPONSES)
def post_transfer_acknowledgement(id: uuid.UUID, req: TransferAcknowledgeRequest, db: DB, user: VaultOperator):
    """Receiver acknowledges transfer and signs for metal custody."""
    ev = get_in_org(db, MaterialEvent, user.organisation_id, id, "Transfer event")
    ack_ev = acknowledge_transfer(db, user, ev, req)
    db.commit()
    return _to_transfer_out(db, ev)


@router.post("/{id}/reverse", response_model=TransferOut, responses=ERROR_RESPONSES)
def post_transfer_reversal(id: uuid.UUID, req: TransferReverseRequest, db: DB, user: Manager):
    """Correct a transfer by appending a compensating mirror reversal event."""
    ev = get_in_org(db, MaterialEvent, user.organisation_id, id, "Transfer event")
    rev_ev = reverse_transfer(db, user, ev, req)
    db.commit()
    return _to_transfer_out(db, ev)
