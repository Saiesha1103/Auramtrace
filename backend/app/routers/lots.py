import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from ..deps import DB, CurrentUser, VaultOperator
from ..models import MaterialLot
from ..schemas import ERROR_RESPONSES, EventOut, IssueRequest, LotCreate, LotOut, Page
from ..services import custody
from ..services.views import events_out, lot_out

router = APIRouter(prefix="/lots", tags=["Gold lots & issuance"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[LotOut], summary="List lots with vault / karigar balances")
def list_lots(
    user: CurrentUser,
    db: DB,
    q: str | None = Query(None, max_length=80, description="Search code or source"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[LotOut]:
    stmt = select(MaterialLot).where(MaterialLot.organisation_id == user.organisation_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(MaterialLot.code).like(like), func.lower(func.coalesce(MaterialLot.source, "")).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(MaterialLot.created_at.desc()).limit(limit).offset(offset))
    return Page(items=[lot_out(db, lot) for lot in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=LotOut, status_code=status.HTTP_201_CREATED, summary="Receive a gold lot into the vault (admin, manager, vault operator)")
def create_lot(body: LotCreate, user: VaultOperator, db: DB) -> LotOut:
    """Records gross, net metal and fineness separately; fine gold = net × fineness ÷ 1000.
    Appends a `lot_received` event (external → vault)."""
    lot = custody.create_lot(db, user, body)
    db.commit()
    return lot_out(db, lot)


@router.get("/{lot_id}", response_model=LotOut, summary="Lot with current balances")
def get_lot(lot_id: uuid.UUID, user: CurrentUser, db: DB) -> LotOut:
    return lot_out(db, custody.get_in_org(db, MaterialLot, user.organisation_id, lot_id, "Lot"))


@router.post("/{lot_id}/issue", response_model=EventOut, status_code=status.HTTP_201_CREATED, summary="Issue metal from a lot to a karigar against a job (admin, manager, vault operator)")
def issue_from_lot(lot_id: uuid.UUID, body: IssueRequest, user: VaultOperator, db: DB) -> EventOut:
    """Appends an `issue` event (vault → karigar). Fails with `insufficient_balance` if the lot's vault
    balance is too low. The issue stays *pending acknowledgement* until the receiver signs for it."""
    lot = custody.get_in_org(db, MaterialLot, user.organisation_id, lot_id, "Lot")
    ev = custody.issue(db, user, lot, body)
    db.commit()
    return events_out(db, [ev])[0]
