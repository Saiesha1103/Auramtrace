import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from ..deps import DB, CurrentUser, Manager
from ..errors import BusinessRuleViolation
from ..models import JobOrder, JobStatus, Karigar, KarigarKind
from ..schemas import ERROR_RESPONSES, JobCreate, JobDetail, JobOut, JobUpdate, Page
from ..services import audit
from ..services.codes import ensure_unique_code, next_code
from ..services.custody import get_in_org
from ..services.ledger import job_issued_total
from ..services.views import job_detail

router = APIRouter(prefix="/jobs", tags=["Jobs"], responses=ERROR_RESPONSES)


def _check_head(db, org_id: uuid.UUID, head_id: uuid.UUID | None) -> None:
    if head_id is None:
        return
    head = get_in_org(db, Karigar, org_id, head_id, "Head karigar")
    if head.kind != KarigarKind.head_karigar:
        raise BusinessRuleViolation(f"{head.code} is not a head karigar", code="invalid_hierarchy")


@router.get("", response_model=Page[JobOut], summary="List jobs")
def list_jobs(
    user: CurrentUser,
    db: DB,
    status_: JobStatus | None = Query(None, alias="status"),
    head_karigar_id: uuid.UUID | None = Query(None, alias="headKarigarId"),
    q: str | None = Query(None, max_length=80, description="Search code, title, order ref"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[JobOut]:
    stmt = select(JobOrder).where(JobOrder.organisation_id == user.organisation_id)
    if status_:
        stmt = stmt.where(JobOrder.status == status_)
    if head_karigar_id:
        stmt = stmt.where(JobOrder.head_karigar_id == head_karigar_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(JobOrder.code).like(like), func.lower(JobOrder.title).like(like), func.lower(func.coalesce(JobOrder.order_ref, "")).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(JobOrder.due_date, JobOrder.code).limit(limit).offset(offset))
    return Page(items=[JobOut.model_validate(j) for j in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED, summary="Create a job order (admin, manager)")
def create_job(body: JobCreate, user: Manager, db: DB) -> JobOut:
    org = user.organisation_id
    _check_head(db, org, body.head_karigar_id)
    code = ensure_unique_code(db, JobOrder, org, body.code) if body.code else next_code(db, JobOrder, org, "J")
    data = body.model_dump(exclude={"code"})
    job = JobOrder(organisation_id=org, code=code, created_by_id=user.id, status=JobStatus.draft, **data)
    db.add(job)
    db.flush()
    audit.record(db, user, org, "job.created", "job_order", job.id, {"code": code, **data})
    db.commit()
    return JobOut.model_validate(job)


@router.get("/{job_id}", response_model=JobDetail, summary="Job details with issued totals, current custody and full event history")
def get_job(job_id: uuid.UUID, user: CurrentUser, db: DB) -> JobDetail:
    return job_detail(db, get_in_org(db, JobOrder, user.organisation_id, job_id, "Job"))


@router.patch("/{job_id}", response_model=JobOut, summary="Edit specification fields, or cancel a job with no gold issued (admin, manager)")
def update_job(job_id: uuid.UUID, body: JobUpdate, user: Manager, db: DB) -> JobOut:
    job = get_in_org(db, JobOrder, user.organisation_id, job_id, "Job")
    changes = body.model_dump(exclude_unset=True)
    if job.status == JobStatus.cancelled:
        raise BusinessRuleViolation("Cancelled jobs cannot be edited", code="job_cancelled")
    if "head_karigar_id" in changes:
        _check_head(db, user.organisation_id, changes["head_karigar_id"])
    if changes.get("status") == "cancelled":
        if job_issued_total(db, job.id).net != 0:
            raise BusinessRuleViolation("Gold is issued against this job; reverse or return it before cancelling", code="job_has_custody")
        changes["status"] = JobStatus.cancelled
    diff = {}
    for k, v in changes.items():
        if v is None and k not in ("notes", "order_ref", "process", "head_karigar_id"):
            continue
        if getattr(job, k) != v:
            diff[k] = {"from": getattr(job, k), "to": v}
            setattr(job, k, v)
    if diff:
        audit.record(db, user, user.organisation_id, "job.updated", "job_order", job.id, diff)
    db.commit()
    return JobOut.model_validate(job)
