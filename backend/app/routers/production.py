"""Production process tracking, manufacturing stages, and physical measurements."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, VaultOperator
from ..models import (
    Karigar,
    ProductionEntry,
    ProductionMeasurement,
)
from ..schemas import (
    ERROR_RESPONSES,
    Page,
    ProductionEntryCreate,
    ProductionEntryOut,
    ProductionEntryUpdate,
    ProductionMeasurementCreate,
    ProductionMeasurementOut,
)
from ..services.custody import get_in_org
from ..services.production import (
    complete_production_entry,
    create_production_entry,
    create_production_measurement,
    list_production_entries,
    list_production_measurements,
    update_production_entry,
)

router = APIRouter(prefix="/production", tags=["production"])


def _to_entry_out(entry: ProductionEntry) -> ProductionEntryOut:
    return ProductionEntryOut(
        id=entry.id,
        job_id=entry.job_id,
        karigar_id=entry.karigar_id,
        karigar_name=entry.karigar.name,
        stage=entry.stage,
        status=entry.status,
        started_at=entry.started_at,
        completed_at=entry.completed_at,
        note=entry.note,
        measurements_count=len(entry.measurements) if entry.measurements else 0,
        created_at=entry.created_at,
    )


def _to_meas_out(m: ProductionMeasurement) -> ProductionMeasurementOut:
    return ProductionMeasurementOut(
        id=m.id,
        production_entry_id=m.production_entry_id,
        job_id=m.job_id,
        karigar_id=m.karigar_id,
        stage=m.stage,
        input_gross_weight_g=m.input_gross_weight_g,
        input_net_metal_weight_g=m.input_net_metal_weight_g,
        output_gross_weight_g=m.output_gross_weight_g,
        output_net_metal_weight_g=m.output_net_metal_weight_g,
        stone_weight_g=m.stone_weight_g,
        alloy_weight_g=m.alloy_weight_g,
        fineness_ppt=m.fineness_ppt,
        pieces=m.pieces,
        scale_id=m.scale_id,
        operator_name=m.operator_name,
        measurement_method=m.measurement_method,
        evidence_ref=m.evidence_ref,
        notes=m.notes,
        is_superseded=m.is_superseded,
        superseded_by_id=m.superseded_by_id,
        correction_reason=m.correction_reason,
        recorded_at=m.recorded_at,
        created_at=m.created_at,
    )


@router.post("", response_model=ProductionEntryOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
@router.post("/entries", response_model=ProductionEntryOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES, include_in_schema=False)
def post_production_entry(req: ProductionEntryCreate, db: DB, user: VaultOperator):
    """Start or record a production stage for a job with a karigar."""
    entry = create_production_entry(db, user, req)
    db.commit()
    return _to_entry_out(entry)


@router.get("", response_model=Page[ProductionEntryOut], responses=ERROR_RESPONSES)
@router.get("/entries", response_model=Page[ProductionEntryOut], responses=ERROR_RESPONSES, include_in_schema=False)
def get_production_entries(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List production stage entries scoped to caller's organisation."""
    stmt = select(ProductionEntry).where(ProductionEntry.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(ProductionEntry.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(ProductionEntry.karigar_id == karigar_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ProductionEntry.started_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_entry_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.post("/measurements", response_model=ProductionMeasurementOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_production_measurement(req: ProductionMeasurementCreate, db: DB, user: VaultOperator):
    """Record physical manufacturing measurement (input/output weights, alloy, stones, operator, scale)."""
    meas = create_production_measurement(db, user, req)
    db.commit()
    return _to_meas_out(meas)


@router.get("/measurements", response_model=Page[ProductionMeasurementOut], responses=ERROR_RESPONSES)
def get_production_measurements(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(ProductionMeasurement).where(ProductionMeasurement.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(ProductionMeasurement.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(ProductionMeasurement.karigar_id == karigar_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ProductionMeasurement.recorded_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_meas_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=ProductionEntryOut, responses=ERROR_RESPONSES)
def get_production_entry_by_id(id: uuid.UUID, db: DB, user: CurrentUser):
    entry = get_in_org(db, ProductionEntry, user.organisation_id, id, "Production entry")
    return _to_entry_out(entry)


@router.patch("/{id}", response_model=ProductionEntryOut, responses=ERROR_RESPONSES)
def patch_production_entry(id: uuid.UUID, req: ProductionEntryUpdate, db: DB, user: VaultOperator):
    entry = get_in_org(db, ProductionEntry, user.organisation_id, id, "Production entry")
    updated = update_production_entry(db, user, entry, req)
    db.commit()
    return _to_entry_out(updated)


@router.post("/{id}/complete", response_model=ProductionEntryOut, responses=ERROR_RESPONSES)
def post_complete_production_entry(id: uuid.UUID, db: DB, user: VaultOperator):
    entry = get_in_org(db, ProductionEntry, user.organisation_id, id, "Production entry")
    completed = complete_production_entry(db, user, entry)
    db.commit()
    return _to_entry_out(completed)
