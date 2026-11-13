"""AI Investigation Assistant endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager
from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    ExceptionCase,
    InvestigationRun,
)
from ..schemas import (
    ERROR_RESPONSES,
    InvestigationRunOut,
    InvestigationRunRequest,
    Page,
)
from ..services.ai_investigation import (
    list_investigations,
    run_investigation,
    tool_calculate_fine_gold_balance,
    tool_compare_measurements,
    tool_get_exception_details,
    tool_get_job_ledger,
    tool_get_job_summary,
    tool_get_material_event_history,
    tool_get_material_returns,
    tool_get_production_measurements,
    tool_get_reconciliation,
    tool_get_transfer_history,
    tool_trace_karigar_custody,
    tool_trace_material_lot,
)
from ..services.custody import get_in_org

router = APIRouter(prefix="/investigations", tags=["ai-investigation"])


def _to_run_out(r: InvestigationRun) -> InvestigationRunOut:
    return InvestigationRunOut(
        id=r.id,
        exception_id=r.exception_id,
        job_id=r.job_id,
        provider=r.provider,
        response=r.response_json,
        confidence=r.confidence,
        created_at=r.created_at,
    )


@router.post("/run", response_model=InvestigationRunOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_run_investigation(req: InvestigationRunRequest, db: DB, user: Manager):
    """Trigger the AI Investigation Assistant for an exception case.
    Executes controlled read-only tools and grounds facts in actual database evidence."""
    run = run_investigation(db, user, req.exception_id)
    db.commit()
    return _to_run_out(run)


@router.get("", response_model=Page[InvestigationRunOut], responses=ERROR_RESPONSES)
def get_investigation_runs(
    db: DB,
    user: CurrentUser,
    exception_id: uuid.UUID | None = Query(None, alias="exceptionId"),
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(InvestigationRun).where(InvestigationRun.organisation_id == user.organisation_id)
    if exception_id:
        stmt = stmt.where(InvestigationRun.exception_id == exception_id)
    if job_id:
        stmt = stmt.where(InvestigationRun.job_id == job_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(InvestigationRun.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_run_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=InvestigationRunOut, responses=ERROR_RESPONSES)
def get_investigation_by_id(id: uuid.UUID, db: DB, user: CurrentUser):
    run = get_in_org(db, InvestigationRun, user.organisation_id, id, "Investigation run")
    return _to_run_out(run)


@router.get("/tools/{tool_name}", responses=ERROR_RESPONSES)
def run_read_only_tool(
    tool_name: str,
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    lot_id: uuid.UUID | None = Query(None, alias="lotId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId"),
    exception_id: uuid.UUID | None = Query(None, alias="exceptionId"),
):
    """Controlled interface to execute AI read-only inspection tools directly."""
    org = user.organisation_id
    if tool_name == "get_job_summary" and job_id:
        return tool_get_job_summary(db, org, job_id)
    elif tool_name == "get_job_ledger" and job_id:
        return tool_get_job_ledger(db, org, job_id)
    elif tool_name == "trace_material_lot" and lot_id:
        return tool_trace_material_lot(db, org, lot_id)
    elif tool_name == "trace_karigar_custody" and karigar_id:
        return tool_trace_karigar_custody(db, org, karigar_id)
    elif tool_name == "get_production_measurements" and job_id:
        return tool_get_production_measurements(db, org, job_id)
    elif tool_name == "get_material_returns" and job_id:
        return tool_get_material_returns(db, org, job_id)
    elif tool_name == "get_reconciliation" and job_id:
        return tool_get_reconciliation(db, org, job_id)
    elif tool_name == "get_exception_details" and exception_id:
        return tool_get_exception_details(db, org, exception_id)
    elif tool_name == "compare_measurements" and job_id:
        return tool_compare_measurements(db, org, job_id)
    elif tool_name == "calculate_fine_gold_balance" and job_id:
        return tool_calculate_fine_gold_balance(db, org, job_id)
    elif tool_name == "get_material_event_history" and job_id:
        return tool_get_material_event_history(db, org, job_id)
    elif tool_name == "get_transfer_history" and job_id:
        return tool_get_transfer_history(db, org, job_id)
    else:
        raise NotFound(f"Tool '{tool_name}' not recognized or missing required parameter")
