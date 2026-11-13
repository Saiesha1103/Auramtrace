"""Exception detection and lifecycle management service.

Automatically detects:
  * Material variances exceeding loss allowances
  * Purity / fineness shortfalls between declared and assayed values
  * Unacknowledged transfers and issues exceeding time thresholds
  * Overdue jobs holding open metal custody
  * Inconsistent returns or outstanding WIP after job closure

Provides:
  * Investigator assignment
  * Investigation notes and status tracking
  * Evidence association
  * Human-authorized resolution and dismissal with mandatory audit logs
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    ExceptionCase,
    ExceptionEvidence,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    JobOrder,
    JobStatus,
    Karigar,
    MaterialEvent,
    MaterialEventType,
    MaterialReturn,
    ReconciliationRun,
    ReconciliationStatus,
    User,
)
from ..models.base import utcnow
from . import audit
from .codes import ensure_unique_code, next_code
from .custody import get_in_org
from .ledger import followups, job_holdings


def detect_exceptions_for_job(db: Session, user: User, job: JobOrder) -> list[ExceptionCase]:
    """Scan a job for workflow discrepancies and reconciliation anomalies."""
    org = user.organisation_id
    now = utcnow()
    created_cases: list[ExceptionCase] = []

    # 1. Reconciliation Variance Exception
    latest_run = db.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.organisation_id == org,
            ReconciliationRun.job_id == job.id,
            ReconciliationRun.is_latest == True,
        )
    )
    if latest_run and latest_run.unexplained_variance_fine_g > latest_run.loss_allowance_fine_g:
        diff = latest_run.unexplained_variance_fine_g - latest_run.loss_allowance_fine_g
        code = f"EX-{job.code[:14]}-V"[:24]
        sev = ExceptionSeverity.critical if diff >= Decimal("0.500") else (ExceptionSeverity.high if diff >= Decimal("0.100") else ExceptionSeverity.medium)
        existing = db.scalar(select(ExceptionCase).where(ExceptionCase.organisation_id == org, ExceptionCase.code == code))
        if not existing:
            ex = ExceptionCase(
                organisation_id=org,
                code=code,
                job_id=job.id,
                karigar_id=job.head_karigar_id,
                lot_id=None,
                exception_type=ExceptionType.variance,
                severity=sev,
                status=ExceptionStatus.open,
                description=f"{float(latest_run.unexplained_variance_fine_g):.3f} g fine gold unexplained variance exceeds {float(latest_run.loss_allowance_fine_g):.3f} g allowance ({float(job.loss_allowance_pct):.1f}%)",
                expected_value=f"<= {float(latest_run.loss_allowance_fine_g):.3f} g fine",
                observed_value=f"{float(latest_run.unexplained_variance_fine_g):.3f} g fine",
                variance_amount_g=diff,
                supporting_event_ids=latest_run.supporting_event_ids,
                supporting_record_ids=[str(latest_run.id)],
            )
            db.add(ex)
            created_cases.append(ex)
        elif existing.status == ExceptionStatus.open:
            existing.severity = sev
            existing.description = f"{float(latest_run.unexplained_variance_fine_g):.3f} g fine gold unexplained variance exceeds {float(latest_run.loss_allowance_fine_g):.3f} g allowance ({float(job.loss_allowance_pct):.1f}%)"
            existing.observed_value = f"{float(latest_run.unexplained_variance_fine_g):.3f} g fine"
            existing.variance_amount_g = diff
            rec_ids = list(existing.supporting_record_ids or [])
            if str(latest_run.id) not in rec_ids:
                rec_ids.append(str(latest_run.id))
                existing.supporting_record_ids = rec_ids

    # 2. Purity / Fineness Mismatch on returns
    returns = list(
        db.scalars(select(MaterialReturn).where(MaterialReturn.organisation_id == org, MaterialReturn.job_id == job.id))
    )
    for r in returns:
        if r.assayed_fineness_ppt is not None and (r.declared_fineness_ppt - r.assayed_fineness_ppt) >= Decimal("20.0"):
            diff_ppt = r.declared_fineness_ppt - r.assayed_fineness_ppt
            deficit_fine = (r.net_metal_weight_g * diff_ppt / Decimal("1000.0")).quantize(Decimal("0.001"))
            code = f"EX-{job.code[:8]}-P-{r.code[-8:]}"[:24]
            existing = db.scalar(select(ExceptionCase).where(ExceptionCase.organisation_id == org, ExceptionCase.code == code))
            if not existing:
                ex = ExceptionCase(
                    organisation_id=org,
                    code=code,
                    job_id=job.id,
                    karigar_id=r.karigar_id,
                    lot_id=r.lot_id,
                    exception_type=ExceptionType.purity_mismatch,
                    severity=ExceptionSeverity.medium,
                    status=ExceptionStatus.open,
                    description=f"Return {r.code} declared {float(r.declared_fineness_ppt):.1f} ppt but assayed {float(r.assayed_fineness_ppt):.1f} ppt (deficit of {float(deficit_fine):.3f} g fine gold)",
                    expected_value=f"{float(r.declared_fineness_ppt):.1f} ppt",
                    observed_value=f"{float(r.assayed_fineness_ppt):.1f} ppt",
                    variance_amount_g=deficit_fine,
                    supporting_event_ids=[str(r.material_event_id)],
                    supporting_record_ids=[str(r.id)],
                )
                db.add(ex)
                created_cases.append(ex)
            elif existing.status == ExceptionStatus.open:
                existing.description = f"Return {r.code} declared {float(r.declared_fineness_ppt):.1f} ppt but assayed {float(r.assayed_fineness_ppt):.1f} ppt (deficit of {float(deficit_fine):.3f} g fine gold)"
                existing.observed_value = f"{float(r.assayed_fineness_ppt):.1f} ppt"
                existing.variance_amount_g = deficit_fine

    # 3. Unacknowledged transfers and issues (older than 2 days)
    events = list(
        db.scalars(
            select(MaterialEvent).where(
                MaterialEvent.organisation_id == org,
                MaterialEvent.job_id == job.id,
                MaterialEvent.event_type.in_([MaterialEventType.issue, MaterialEventType.transfer]),
            )
        )
    )
    fu = followups(db, [e.id for e in events])
    threshold = now - timedelta(days=2)
    for e in events:
        if fu[e.id].reversal_id is None and (fu[e.id].acknowledgement_id is None or fu[e.id].acknowledgement_reversed):
            # Check if pending or overdue
            code = f"EX-{job.code[:8]}-U-{str(e.id)[:8]}"[:24]
            existing = db.scalar(select(ExceptionCase).where(ExceptionCase.organisation_id == org, ExceptionCase.code == code))
            if not existing:
                rec = e.recorded_at if e.recorded_at.tzinfo is not None else e.recorded_at.replace(tzinfo=UTC)
                is_old = rec <= threshold
                ex_type = ExceptionType.unacknowledged_issue if e.event_type == MaterialEventType.issue else ExceptionType.unacknowledged_transfer
                ex = ExceptionCase(
                    organisation_id=org,
                    code=code,
                    job_id=job.id,
                    karigar_id=e.to_karigar_id,
                    lot_id=e.lot_id,
                    exception_type=ex_type,
                    severity=ExceptionSeverity.medium if is_old else ExceptionSeverity.low,
                    status=ExceptionStatus.open,
                    description=f"Material {e.event_type.value} of {float(e.net_weight_g or 0):.3f} g has not been acknowledged by receiver",
                    expected_value="Receiver signed acknowledgement",
                    observed_value="Pending signature",
                    variance_amount_g=e.fine_gold_g,
                    supporting_event_ids=[str(e.id)],
                    supporting_record_ids=[],
                )
                db.add(ex)
                created_cases.append(ex)

    # 4. Overdue job with outstanding WIP
    if job.due_date < now.date() and job.status in (JobStatus.draft, JobStatus.issued, JobStatus.in_production):
        code = f"EX-{job.code[:14]}-DUE"[:24]
        existing = db.scalar(select(ExceptionCase).where(ExceptionCase.organisation_id == org, ExceptionCase.code == code))
        if not existing:
            holdings = job_holdings(db, job.id)
            total_held = sum((h.fine for h in holdings.values()), Decimal("0.000"))
            ex = ExceptionCase(
                organisation_id=org,
                code=code,
                job_id=job.id,
                karigar_id=job.head_karigar_id,
                lot_id=None,
                exception_type=ExceptionType.overdue_job,
                severity=ExceptionSeverity.low,
                status=ExceptionStatus.open,
                description=f"Job target due date {job.due_date} has passed while job remains in status '{job.status.value}' with {float(total_held):.3f} g fine WIP held by karigars",
                expected_value=f"Completed before {job.due_date}",
                observed_value=f"Status: {job.status.value}",
                variance_amount_g=total_held,
                supporting_event_ids=[],
                supporting_record_ids=[str(job.id)],
            )
            db.add(ex)
            created_cases.append(ex)

    db.flush()
    return created_cases


def list_exceptions(
    db: Session,
    org_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    status: ExceptionStatus | None = None,
    severity: ExceptionSeverity | None = None,
    exception_type: ExceptionType | None = None,
) -> list[ExceptionCase]:
    stmt = select(ExceptionCase).where(ExceptionCase.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(ExceptionCase.job_id == job_id)
    if status:
        stmt = stmt.where(ExceptionCase.status == status)
    if severity:
        stmt = stmt.where(ExceptionCase.severity == severity)
    if exception_type:
        stmt = stmt.where(ExceptionCase.exception_type == exception_type)
    return list(db.scalars(stmt.order_by(ExceptionCase.created_at.desc())))


def assign_investigator(db: Session, user: User, case: ExceptionCase, investigator_id: uuid.UUID) -> ExceptionCase:
    investigator = get_in_org(db, User, user.organisation_id, investigator_id, "Investigator user")
    case.assigned_investigator_id = investigator.id
    if case.status == ExceptionStatus.open:
        case.status = ExceptionStatus.investigating
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.assigned",
        "exception_case",
        case.id,
        {"investigatorEmail": investigator.email, "status": case.status.value},
    )
    return case


def update_exception_status(db: Session, user: User, case: ExceptionCase, new_status: ExceptionStatus, notes: str | None = None) -> ExceptionCase:
    case.status = new_status
    if notes:
        case.investigation_notes = f"{case.investigation_notes or ''}\n[{utcnow().isoformat()}] {notes}".strip()
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.status_updated",
        "exception_case",
        case.id,
        {"newStatus": new_status.value},
    )
    return case


def add_investigation_notes(db: Session, user: User, case: ExceptionCase, notes: str) -> ExceptionCase:
    ts = utcnow().isoformat()
    case.investigation_notes = f"{case.investigation_notes or ''}\n[{ts} - {user.full_name}]: {notes}".strip()
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.notes_added",
        "exception_case",
        case.id,
        {"notesLength": len(notes)},
    )
    return case


def resolve_exception(db: Session, user: User, case: ExceptionCase, resolution_notes: str) -> ExceptionCase:
    case.status = ExceptionStatus.resolved
    case.resolution_notes = resolution_notes
    case.resolution_timestamp = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.resolved",
        "exception_case",
        case.id,
        {"resolutionNotes": resolution_notes},
    )
    return case


def dismiss_exception(db: Session, user: User, case: ExceptionCase, reason: str) -> ExceptionCase:
    if not reason or len(reason.strip()) < 4:
        raise BusinessRuleViolation("A valid reason is required to dismiss an exception", code="missing_dismissal_reason")
    case.status = ExceptionStatus.dismissed
    case.dismissal_reason = reason
    case.resolution_timestamp = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.dismissed",
        "exception_case",
        case.id,
        {"dismissalReason": reason},
    )
    return case


def add_exception_evidence(
    db: Session,
    user: User,
    case: ExceptionCase,
    evidence_type: str,
    title: str,
    file_url: str | None = None,
    details: dict[str, Any] | None = None,
) -> ExceptionEvidence:
    ev = ExceptionEvidence(
        organisation_id=user.organisation_id,
        exception_id=case.id,
        evidence_type=evidence_type,
        title=title,
        file_url=file_url,
        details=details or {},
    )
    db.add(ev)
    db.flush()
    audit.record(
        db,
        user,
        case.organisation_id,
        "exception.evidence_added",
        "exception_evidence",
        ev.id,
        {"evidenceType": evidence_type, "title": title},
    )
    return ev
