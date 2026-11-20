"""Karigar portal: each karigar's full view of their OWN account, and nothing else.

Every query here is scoped by the signed-in user's linked karigar id (never by a request
parameter), so a karigar can see and respond to their own gold, jobs and settlements only.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from ..deps import DB, KarigarUser
from ..errors import NotFound
from ..models import Karigar, MaterialEvent, MaterialEventType, SettlementWorksheet
from ..schemas import (
    ERROR_RESPONSES,
    AcknowledgeRequest,
    CamelModel,
    EventOut,
    JobOut,
    KarigarAcceptRequest,
    KarigarDisputeRequest,
    KarigarProfile,
    SettlementWorksheetOut,
    TransferAcknowledgeRequest,
)
from ..services import custody, transfers
from ..services.settlements import karigar_accept_worksheet, karigar_dispute_worksheet
from ..services.track_record import karigar_jobs, track_record
from ..services.views import events_out, karigar_profile
from .settlements import _to_sheet_out

router = APIRouter(prefix="/portal", tags=["karigar portal"], responses=ERROR_RESPONSES)


class PortalMe(CamelModel):
    full_name: str
    email: str
    karigar: KarigarProfile
    track_record: dict[str, Any]


class PortalAckRequest(CamelModel):
    evidence_ref: str | None = Field(default=None, max_length=200, examples=["Weighed on my scale: 30.151 g"])
    note: str | None = Field(default=None, max_length=2000)


def _me(db: DB, user) -> Karigar:
    k = db.get(Karigar, user.karigar_id)
    if k is None or k.organisation_id != user.organisation_id:
        raise NotFound("Karigar account not found")
    return k


@router.get("/me", response_model=PortalMe, summary="My profile, the gold I hold right now, and my track record")
def get_me(user: KarigarUser, db: DB) -> PortalMe:
    k = _me(db, user)
    return PortalMe(full_name=user.full_name, email=user.email, karigar=karigar_profile(db, k), track_record=track_record(db, user.organisation_id, k.id))


@router.get("/jobs", response_model=list[JobOut], summary="Jobs I am responsible for")
def get_my_jobs(user: KarigarUser, db: DB) -> list[JobOut]:
    return [JobOut.model_validate(j) for j in karigar_jobs(db, user.organisation_id, user.karigar_id)]


@router.get("/ledger", response_model=list[EventOut], summary="Every gold movement to or from me, newest first")
def get_my_ledger(user: KarigarUser, db: DB, limit: int = Query(200, ge=1, le=500)) -> list[EventOut]:
    kid = user.karigar_id
    rows = list(
        db.scalars(
            select(MaterialEvent)
            .where(MaterialEvent.organisation_id == user.organisation_id, (MaterialEvent.to_karigar_id == kid) | (MaterialEvent.from_karigar_id == kid))
            .order_by(MaterialEvent.recorded_at.desc())
            .limit(limit)
        )
    )
    return events_out(db, rows)


@router.post("/events/{event_id}/acknowledge", response_model=EventOut, status_code=status.HTTP_201_CREATED, summary="Confirm I received gold issued or transferred to me")
def acknowledge_receipt(event_id: uuid.UUID, body: PortalAckRequest, user: KarigarUser, db: DB) -> EventOut:
    ev = db.get(MaterialEvent, event_id)
    if ev is None or ev.organisation_id != user.organisation_id or ev.to_karigar_id != user.karigar_id:
        raise NotFound("Event not found")
    if ev.event_type == MaterialEventType.transfer:
        ack = transfers.acknowledge_transfer(db, user, ev, TransferAcknowledgeRequest(acknowledged_by_name=user.full_name, evidence_ref=body.evidence_ref, note=body.note))
    else:
        ack = custody.acknowledge(db, user, ev, AcknowledgeRequest(acknowledged_by_name=user.full_name, evidence_ref=body.evidence_ref, note=body.note))
    db.commit()
    return events_out(db, [ack])[0]


@router.get("/settlements", response_model=list[SettlementWorksheetOut], summary="My settlements, including ones waiting for my response")
def get_my_settlements(user: KarigarUser, db: DB) -> list[SettlementWorksheetOut]:
    rows = db.scalars(
        select(SettlementWorksheet)
        .where(SettlementWorksheet.organisation_id == user.organisation_id, SettlementWorksheet.karigar_id == user.karigar_id)
        .order_by(SettlementWorksheet.created_at.desc())
    )
    return [_to_sheet_out(w) for w in rows]


def _my_sheet(db: DB, user, sheet_id: uuid.UUID) -> SettlementWorksheet:
    w = db.get(SettlementWorksheet, sheet_id)
    if w is None or w.organisation_id != user.organisation_id or w.karigar_id != user.karigar_id:
        raise NotFound("Settlement worksheet not found")
    return w


@router.post("/settlements/{sheet_id}/accept", response_model=SettlementWorksheetOut, summary="Accept a jeweller-approved settlement (second-party approval)")
def accept_settlement(sheet_id: uuid.UUID, body: KarigarAcceptRequest, user: KarigarUser, db: DB) -> SettlementWorksheetOut:
    w = karigar_accept_worksheet(db, user, _my_sheet(db, user, sheet_id), body.note)
    db.commit()
    return _to_sheet_out(w)


@router.post("/settlements/{sheet_id}/dispute", response_model=SettlementWorksheetOut, summary="Dispute a settlement, with my reason on record")
def dispute_settlement(sheet_id: uuid.UUID, body: KarigarDisputeRequest, user: KarigarUser, db: DB) -> SettlementWorksheetOut:
    w = karigar_dispute_worksheet(db, user, _my_sheet(db, user, sheet_id), body.reason)
    db.commit()
    return _to_sheet_out(w)
