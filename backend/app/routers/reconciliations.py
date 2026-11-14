"""Fine-gold reconciliation engine endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager
from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    JobOrder,
    ReconciliationLineItem,
    ReconciliationRun,
)
from ..schemas import (
    ERROR_RESPONSES,
    Page,
    ReconciliationLineItemOut,
    ReconciliationRunOut,
    ReconciliationSummaryOut,
)
from ..services.custody import get_in_org
from ..services.reconciliation import (
    get_latest_reconciliation,
    get_reconciliation_summary,
    list_reconciliation_runs,
    run_reconciliation,
)

router = APIRouter(tags=["reconciliation"])


def _to_recon_out(r: ReconciliationRun) -> ReconciliationRunOut:
    line_items = [
        ReconciliationLineItemOut(
            id=li.id,
            category=li.category,
            karigar_id=li.karigar_id,
            lot_id=li.lot_id,
            gross_weight_g=li.gross_weight_g,
            net_metal_weight_g=li.net_metal_weight_g,
            fineness_ppt=li.fineness_ppt,
            fine_gold_g=li.fine_gold_g,
            notes=li.notes,
        )
        for li in (r.line_items or [])
    ]
    return ReconciliationRunOut(
        id=r.id,
        job_id=r.job_id,
        run_number=r.run_number,
        version_identifier=r.version_identifier,
        status=r.status,
        total_issued_gross_g=r.total_issued_gross_g,
        total_issued_net_g=r.total_issued_net_g,
        total_issued_fine_g=r.total_issued_fine_g,
        finished_jewellery_fine_g=r.finished_jewellery_fine_g,
        returned_scrap_fine_g=r.returned_scrap_fine_g,
        retained_scrap_fine_g=r.retained_scrap_fine_g,
        closing_wip_fine_g=r.closing_wip_fine_g,
        documented_loss_fine_g=r.documented_loss_fine_g,
        expected_fine_g=r.expected_fine_g,
        actual_accounted_fine_g=r.actual_accounted_fine_g,
        unexplained_variance_fine_g=r.unexplained_variance_fine_g,
        variance_pct=r.variance_pct,
        loss_allowance_pct=r.loss_allowance_pct,
        loss_allowance_fine_g=r.loss_allowance_fine_g,
        supporting_event_ids=r.supporting_event_ids,
        supporting_return_ids=r.supporting_return_ids,
        supporting_measurement_ids=r.supporting_measurement_ids,
        calculation_details=r.calculation_details,
        is_latest=r.is_latest,
        created_at=r.created_at,
        line_items=line_items,
    )


@router.post("/jobs/{id}/reconcile", response_model=ReconciliationRunOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_reconciliation_for_job(id: uuid.UUID, db: DB, user: Manager):
    """Execute deterministic fine-gold reconciliation equation for a job and persist an immutable snapshot."""
    job = get_in_org(db, JobOrder, user.organisation_id, id, "Job")
    recon = run_reconciliation(db, user, job)
    db.commit()
    return _to_recon_out(recon)


@router.get("/jobs/{id}/reconciliation", response_model=ReconciliationRunOut, responses=ERROR_RESPONSES)
def get_job_reconciliation(id: uuid.UUID, db: DB, user: CurrentUser):
    """Retrieve the latest fine-gold reconciliation snapshot for a job."""
    job = get_in_org(db, JobOrder, user.organisation_id, id, "Job")
    recon = get_latest_reconciliation(db, user.organisation_id, job.id)
    if not recon:
        raise NotFound("No reconciliation run found for this job")
    return _to_recon_out(recon)


@router.get("/reconciliations", response_model=Page[ReconciliationRunOut], responses=ERROR_RESPONSES)
def get_reconciliations(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List historical reconciliation snapshots."""
    stmt = select(ReconciliationRun).where(ReconciliationRun.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(ReconciliationRun.job_id == job_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ReconciliationRun.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_recon_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/reconciliations/summary", response_model=ReconciliationSummaryOut, responses=ERROR_RESPONSES)
def get_organisation_reconciliation_summary(db: DB, user: CurrentUser):
    """Retrieve organisation-wide fine-gold reconciliation and variance metrics."""
    return get_reconciliation_summary(db, user.organisation_id)


@router.get("/reconciliations/compare", responses=ERROR_RESPONSES)
def compare_reconciliation_runs(
    db: DB,
    user: CurrentUser,
    run1_id: uuid.UUID = Query(..., alias="run1Id"),
    run2_id: uuid.UUID = Query(..., alias="run2Id"),
):
    """Compare two reconciliation snapshots side-by-side to track material movement changes."""
    r1 = get_in_org(db, ReconciliationRun, user.organisation_id, run1_id, "First reconciliation run")
    r2 = get_in_org(db, ReconciliationRun, user.organisation_id, run2_id, "Second reconciliation run")
    return {
        "run1": _to_recon_out(r1),
        "run2": _to_recon_out(r2),
        "delta": {
            "issuedFineG": float(r2.total_issued_fine_g - r1.total_issued_fine_g),
            "accountedFineG": float(r2.actual_accounted_fine_g - r1.actual_accounted_fine_g),
            "unexplainedVarianceFineG": float(r2.unexplained_variance_fine_g - r1.unexplained_variance_fine_g),
            "statusChanged": r1.status != r2.status,
        },
    }


@router.get("/reconciliations/{id}", response_model=ReconciliationRunOut, responses=ERROR_RESPONSES)
def get_reconciliation_by_id(id: uuid.UUID, db: DB, user: CurrentUser):
    recon = get_in_org(db, ReconciliationRun, user.organisation_id, id, "Reconciliation run")
    return _to_recon_out(recon)
