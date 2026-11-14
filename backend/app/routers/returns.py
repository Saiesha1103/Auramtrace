"""Material return workflows: finished jewellery, scrap, dust, and WIP."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager, VaultOperator
from ..models import (
    MaterialReturn,
    ReturnCategory,
)
from ..schemas import (
    ERROR_RESPONSES,
    MaterialReturnAssayUpdate,
    MaterialReturnCreate,
    MaterialReturnOut,
    Page,
)
from ..services.custody import get_in_org
from ..services.returns import create_return, update_assay_result

router = APIRouter(prefix="/returns", tags=["returns"])


def _to_return_out(r: MaterialReturn) -> MaterialReturnOut:
    return MaterialReturnOut(
        id=r.id,
        code=r.code,
        job_id=r.job_id,
        karigar_id=r.karigar_id,
        lot_id=r.lot_id,
        return_category=r.return_category,
        gross_weight_g=r.gross_weight_g,
        net_metal_weight_g=r.net_metal_weight_g,
        stone_weight_g=r.stone_weight_g,
        declared_fineness_ppt=r.declared_fineness_ppt,
        assayed_fineness_ppt=r.assayed_fineness_ppt,
        fine_gold_g=r.fine_gold_g,
        pieces=r.pieces,
        is_partial=r.is_partial,
        retained_scrap_g=r.retained_scrap_g,
        scale_id=r.scale_id,
        operator_name=r.operator_name,
        measurement_method=r.measurement_method,
        challan_ref=r.challan_ref,
        evidence_ref=r.evidence_ref,
        assay_evidence_ref=r.assay_evidence_ref,
        notes=r.notes,
        material_event_id=r.material_event_id,
        created_at=r.created_at,
    )


@router.post("", response_model=MaterialReturnOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_return(req: MaterialReturnCreate, db: DB, user: VaultOperator):
    """Record physical return of finished jewellery, scrap, dust or WIP from karigar to vault.
    Appends an immutable custody movement event (return_vault)."""
    ret = create_return(db, user, req)
    db.commit()
    return _to_return_out(ret)


@router.get("", response_model=Page[MaterialReturnOut], responses=ERROR_RESPONSES)
def list_material_returns(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId"),
    category: ReturnCategory | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(MaterialReturn).where(MaterialReturn.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(MaterialReturn.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(MaterialReturn.karigar_id == karigar_id)
    if category:
        stmt = stmt.where(MaterialReturn.return_category == category)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(MaterialReturn.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_return_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=MaterialReturnOut, responses=ERROR_RESPONSES)
def get_return(id: uuid.UUID, db: DB, user: CurrentUser):
    ret = get_in_org(db, MaterialReturn, user.organisation_id, id, "Material return")
    return _to_return_out(ret)


@router.post("/{id}/assay", response_model=MaterialReturnOut, responses=ERROR_RESPONSES)
def post_assay_result(id: uuid.UUID, req: MaterialReturnAssayUpdate, db: DB, user: Manager):
    """Record verified assay results (fire assay, spectrometer) for a returned material item."""
    ret = get_in_org(db, MaterialReturn, user.organisation_id, id, "Material return")
    updated = update_assay_result(db, user, ret, req)
    db.commit()
    return _to_return_out(updated)
