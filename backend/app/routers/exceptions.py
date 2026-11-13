"""Exception detection and management router."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager
from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    ExceptionCase,
    ExceptionEvidence,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    JobOrder,
)
from ..schemas.common import CamelModel
from ..schemas import (
    ERROR_RESPONSES,
    ExceptionAssignRequest,
    ExceptionCaseOut,
    ExceptionDismissRequest,
    ExceptionEvidenceOut,
    ExceptionNotesRequest,
    ExceptionResolveRequest,
    ExceptionStatusUpdateRequest,
    Page,
)
from ..services.custody import get_in_org
from ..services.exceptions import (
    add_exception_evidence,
    add_investigation_notes,
    assign_investigator,
    detect_exceptions_for_job,
    dismiss_exception,
    list_exceptions,
    resolve_exception,
    update_exception_status,
)

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


def _to_case_out(c: ExceptionCase) -> ExceptionCaseOut:
    return ExceptionCaseOut(
        id=c.id,
        code=c.code,
        job_id=c.job_id,
        karigar_id=c.karigar_id,
        lot_id=c.lot_id,
        exception_type=c.exception_type,
        severity=c.severity,
        status=c.status,
        description=c.description,
        expected_value=c.expected_value,
        observed_value=c.observed_value,
        variance_amount_g=c.variance_amount_g,
        supporting_event_ids=c.supporting_event_ids or [],
        supporting_record_ids=c.supporting_record_ids or [],
        assigned_investigator_id=c.assigned_investigator_id,
        investigation_notes=c.investigation_notes,
        resolution_notes=c.resolution_notes,
        resolution_timestamp=c.resolution_timestamp,
        dismissal_reason=c.dismissal_reason,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_ev_out(ev: ExceptionEvidence) -> ExceptionEvidenceOut:
    return ExceptionEvidenceOut(
        id=ev.id,
        exception_id=ev.exception_id,
        evidence_type=ev.evidence_type,
        title=ev.title,
        file_url=ev.file_url,
        details=ev.details,
        created_at=ev.created_at,
    )


class EvidenceCreate(CamelModel):
    evidence_type: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=200)
    file_url: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/detect", response_model=list[ExceptionCaseOut], responses=ERROR_RESPONSES)
def trigger_exception_detection(
    db: DB,
    user: Manager,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
):
    """Scan jobs for anomalies, purity shortfalls, unacknowledged transfers, and variances."""
    org = user.organisation_id
    jobs = [get_in_org(db, JobOrder, org, job_id, "Job")] if job_id else list(db.scalars(select(JobOrder).where(JobOrder.organisation_id == org)))
    found = []
    for j in jobs:
        cases = detect_exceptions_for_job(db, user, j)
        found.extend(cases)
    db.commit()
    return [_to_case_out(c) for c in found]


@router.get("", response_model=Page[ExceptionCaseOut], responses=ERROR_RESPONSES)
def get_exceptions(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    status: ExceptionStatus | None = None,
    severity: ExceptionSeverity | None = None,
    exception_type: ExceptionType | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List exceptions raised by reconciliation or custody rules."""
    stmt = select(ExceptionCase).where(ExceptionCase.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(ExceptionCase.job_id == job_id)
    if status:
        stmt = stmt.where(ExceptionCase.status == status)
    if severity:
        stmt = stmt.where(ExceptionCase.severity == severity)
    if exception_type:
        stmt = stmt.where(ExceptionCase.exception_type == exception_type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ExceptionCase.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_case_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def get_exception_by_id(id: uuid.UUID, db: DB, user: CurrentUser):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    return _to_case_out(case)


@router.patch("/{id}/assign", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def patch_assign_investigator(id: uuid.UUID, req: ExceptionAssignRequest, db: DB, user: Manager):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    assigned = assign_investigator(db, user, case, req.investigator_id)
    db.commit()
    return _to_case_out(assigned)


@router.patch("/{id}/status", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def patch_status(id: uuid.UUID, req: ExceptionStatusUpdateRequest, db: DB, user: Manager):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    updated = update_exception_status(db, user, case, req.status, req.notes)
    db.commit()
    return _to_case_out(updated)


@router.post("/{id}/notes", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def post_notes(id: uuid.UUID, req: ExceptionNotesRequest, db: DB, user: Manager):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    updated = add_investigation_notes(db, user, case, req.notes)
    db.commit()
    return _to_case_out(updated)


@router.post("/{id}/resolve", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def post_resolve(id: uuid.UUID, req: ExceptionResolveRequest, db: DB, user: Manager):
    """Mark exception resolved with mandatory resolution notes. Audited."""
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    resolved = resolve_exception(db, user, case, req.resolution_notes)
    db.commit()
    return _to_case_out(resolved)


@router.post("/{id}/dismiss", response_model=ExceptionCaseOut, responses=ERROR_RESPONSES)
def post_dismiss(id: uuid.UUID, req: ExceptionDismissRequest, db: DB, user: Manager):
    """Dismiss exception with mandatory justification. Audited."""
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    dismissed = dismiss_exception(db, user, case, req.reason)
    db.commit()
    return _to_case_out(dismissed)


@router.get("/{id}/evidence", response_model=list[ExceptionEvidenceOut], responses=ERROR_RESPONSES)
def get_evidence(id: uuid.UUID, db: DB, user: CurrentUser):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    evidence = list(db.scalars(select(ExceptionEvidence).where(ExceptionEvidence.exception_id == case.id)))
    return [_to_ev_out(e) for e in evidence]


@router.post("/{id}/evidence", response_model=ExceptionEvidenceOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_evidence(id: uuid.UUID, req: EvidenceCreate, db: DB, user: Manager):
    case = get_in_org(db, ExceptionCase, user.organisation_id, id, "Exception case")
    ev = add_exception_evidence(db, user, case, req.evidence_type, req.title, req.file_url, req.details)
    db.commit()
    return _to_ev_out(ev)
