import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from ..deps import DB, CurrentUser, Manager, VaultOperator
from ..models import MaterialEvent, MaterialEventType
from ..schemas import ERROR_RESPONSES, AcknowledgeRequest, EventOut, Page, ReverseRequest
from ..services import custody
from ..services.views import events_out

router = APIRouter(prefix="/events", tags=["Material events (append-only)"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[EventOut], summary="Material event history, oldest first")
def list_events(
    user: CurrentUser,
    db: DB,
    lot_id: uuid.UUID | None = Query(None, alias="lotId"),
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId", description="Events where the karigar is sender or receiver"),
    event_type: MaterialEventType | None = Query(None, alias="eventType"),
    occurred_from: datetime | None = Query(None, alias="from"),
    occurred_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[EventOut]:
    stmt = select(MaterialEvent).where(MaterialEvent.organisation_id == user.organisation_id)
    if lot_id:
        stmt = stmt.where(MaterialEvent.lot_id == lot_id)
    if job_id:
        stmt = stmt.where(MaterialEvent.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(or_(MaterialEvent.from_karigar_id == karigar_id, MaterialEvent.to_karigar_id == karigar_id))
    if event_type:
        stmt = stmt.where(MaterialEvent.event_type == event_type)
    if occurred_from:
        stmt = stmt.where(MaterialEvent.occurred_at >= occurred_from)
    if occurred_to:
        stmt = stmt.where(MaterialEvent.occurred_at <= occurred_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(db.scalars(stmt.order_by(MaterialEvent.recorded_at, MaterialEvent.id).limit(limit).offset(offset)))
    return Page(items=events_out(db, rows), total=total, limit=limit, offset=offset)


@router.get("/{event_id}", response_model=EventOut, summary="One event with its derived state (reversed / acknowledged)")
def get_event(event_id: uuid.UUID, user: CurrentUser, db: DB) -> EventOut:
    return events_out(db, [custody.get_in_org(db, MaterialEvent, user.organisation_id, event_id, "Event")])[0]


@router.post("/{event_id}/acknowledge", response_model=EventOut, status_code=status.HTTP_201_CREATED, summary="Record the receiver's acknowledgement of an issue (admin, manager, vault operator)")
def acknowledge(event_id: uuid.UUID, body: AcknowledgeRequest, user: VaultOperator, db: DB) -> EventOut:
    """Appends an `issue_acknowledged` event referencing the issue. Each issue can be acknowledged once."""
    ev = custody.acknowledge(db, user, custody.get_in_org(db, MaterialEvent, user.organisation_id, event_id, "Event"), body)
    db.commit()
    return events_out(db, [ev])[0]


@router.post("/{event_id}/reverse", response_model=EventOut, status_code=status.HTTP_201_CREATED, summary="Correct an event by appending a reversal (admin, manager)")
def reverse(event_id: uuid.UUID, body: ReverseRequest, user: Manager, db: DB) -> EventOut:
    """Appends a `reversal` that mirrors the original movement. The original event is never changed or deleted.
    Rules: a reversal can't be reversed; each event is reversed at most once; an acknowledged issue needs its
    acknowledgement reversed first; a receipt can't be reversed while metal from the lot is issued out."""
    ev = custody.reverse(db, user, custody.get_in_org(db, MaterialEvent, user.organisation_id, event_id, "Event"), body)
    db.commit()
    return events_out(db, [ev])[0]
