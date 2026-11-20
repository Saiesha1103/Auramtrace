"""Karigar track record and watch-list queries.

Everything here is derived from records both parties can already see (returns, reconciliations,
settlements, exceptions). Nothing is stored, so the numbers can always be re-checked. These are
the read-only tools the watcher agent uses, and the karigar portal shows the same record to the
karigar it describes.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ExceptionCase,
    ExceptionStatus,
    JobOrder,
    JobStatus,
    Karigar,
    MaterialEvent,
    MaterialReturn,
    ReconciliationRun,
    ReturnCategory,
    SettlementStatus,
    SettlementWorksheet,
)
from ..models.base import utcnow
from .custody import get_in_org
from .ledger import job_holdings, karigar_holding

CLOSED_JOB = (JobStatus.settled, JobStatus.cancelled)
AWAITING_PAYMENT = (SettlementStatus.approved, SettlementStatus.karigar_accepted, SettlementStatus.disputed)


def _aware(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _today() -> date:
    return utcnow().date()


def _finished_returns(db: Session, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[MaterialReturn]]:
    out: dict[uuid.UUID, list[MaterialReturn]] = {}
    if not job_ids:
        return out
    for r in db.scalars(select(MaterialReturn).where(MaterialReturn.job_id.in_(job_ids), MaterialReturn.return_category == ReturnCategory.finished_jewellery)):
        out.setdefault(r.job_id, []).append(r)
    return out


def karigar_jobs(db: Session, org_id: uuid.UUID, karigar_id: uuid.UUID) -> list[JobOrder]:
    """Jobs a karigar is responsible for: head karigar on the job, or returned work on it."""
    returned_job_ids = select(MaterialReturn.job_id).where(MaterialReturn.organisation_id == org_id, MaterialReturn.karigar_id == karigar_id)
    stmt = select(JobOrder).where(
        JobOrder.organisation_id == org_id,
        (JobOrder.head_karigar_id == karigar_id) | (JobOrder.id.in_(returned_job_ids)),
    )
    return list(db.scalars(stmt.order_by(JobOrder.due_date)))


def track_record(db: Session, org_id: uuid.UUID, karigar_id: uuid.UUID) -> dict[str, Any]:
    k = get_in_org(db, Karigar, org_id, karigar_id, "Karigar")
    jobs = karigar_jobs(db, org_id, k.id)
    finished = _finished_returns(db, [j.id for j in jobs])
    # delivery date = when the return movement physically happened, not when the row was typed in
    ev_ids = [r.material_event_id for rs in finished.values() for r in rs]
    occurred = dict(db.execute(select(MaterialEvent.id, MaterialEvent.occurred_at).where(MaterialEvent.id.in_(ev_ids))).all()) if ev_ids else {}

    delivered = on_time = occasion_kept = occasion_jobs = 0
    for j in jobs:
        rets = finished.get(j.id)
        if not rets:
            continue
        delivered += 1
        done = max(_aware(occurred.get(r.material_event_id) or r.created_at) for r in rets).date()
        if done <= j.due_date:
            on_time += 1
        if j.occasion_date:
            occasion_jobs += 1
            if done <= j.occasion_date:
                occasion_kept += 1

    recons = list(
        db.scalars(
            select(ReconciliationRun).where(
                ReconciliationRun.organisation_id == org_id,
                ReconciliationRun.job_id.in_([j.id for j in jobs] or [uuid.uuid4()]),
                ReconciliationRun.is_latest == True,  # noqa: E712
            )
        )
    )
    within = sum(1 for r in recons if r.unexplained_variance_fine_g <= r.loss_allowance_fine_g)
    avg_var = (sum((r.variance_pct for r in recons), Decimal("0")) / len(recons)) if recons else None

    sheets = list(db.scalars(select(SettlementWorksheet).where(SettlementWorksheet.organisation_id == org_id, SettlementWorksheet.karigar_id == k.id)))
    paid_days = [
        (_aware(s.paid_at) - _aware(s.approved_at)).days
        for s in sheets
        if s.status == SettlementStatus.paid and s.paid_at and s.approved_at
    ]
    now = utcnow()
    waiting = [
        {"worksheetId": str(s.id), "code": s.code, "status": s.status.value, "amount": float(s.net_payable_amount), "daysWaiting": (now - _aware(s.approved_at)).days}
        for s in sheets
        if s.status in AWAITING_PAYMENT and s.approved_at
    ]
    disputes = sum(1 for s in sheets if s.dispute_reason)

    exc = list(db.scalars(select(ExceptionCase).where(ExceptionCase.organisation_id == org_id, ExceptionCase.karigar_id == k.id)))
    holding = karigar_holding(db, org_id, k.id)

    return {
        "karigarId": str(k.id),
        "code": k.code,
        "name": k.name,
        "jobsTotal": len(jobs),
        "jobsDelivered": delivered,
        "onTimeDeliveries": on_time,
        "onTimeRatePct": round(100 * on_time / delivered, 1) if delivered else None,
        "occasionJobsDelivered": occasion_jobs,
        "occasionDatesKept": occasion_kept,
        "reconciledJobs": len(recons),
        "withinWastageAllowance": within,
        "withinAllowanceRatePct": round(100 * within / len(recons), 1) if recons else None,
        "averageVariancePct": round(float(avg_var), 3) if avg_var is not None else None,
        "settlements": len(sheets),
        "settlementsDisputed": disputes,
        "settlementsPaid": len(paid_days),
        "averageDaysToPayment": round(sum(paid_days) / len(paid_days), 1) if paid_days else None,
        "awaitingPayment": waiting,
        "exceptionsOpen": sum(1 for e in exc if e.status in (ExceptionStatus.open, ExceptionStatus.investigating)),
        "exceptionsTotal": len(exc),
        "fineGoldHeldG": float(holding.fine),
        "asOf": now.isoformat(),
        "basis": "Derived live from returns, reconciliations, settlements and exceptions; nothing is self-reported.",
    }


# ------------------------------------------------------------------ watcher tools


def jobs_at_risk(db: Session, org_id: uuid.UUID, horizon_days: int = 7) -> list[dict[str, Any]]:
    """Open jobs whose due date or customer occasion date is past, or within ``horizon_days``."""
    today = _today()
    jobs = list(db.scalars(select(JobOrder).where(JobOrder.organisation_id == org_id, JobOrder.status.not_in(CLOSED_JOB))))
    finished = _finished_returns(db, [j.id for j in jobs])
    names = {k.id: (k.code, k.name) for k in db.scalars(select(Karigar).where(Karigar.organisation_id == org_id))}
    out = []
    for j in jobs:
        delivered_pieces = sum(r.pieces or 0 for r in finished.get(j.id, []))
        if delivered_pieces >= j.pieces:
            continue  # all pieces back; nothing to chase
        days_due = (j.due_date - today).days
        days_occ = (j.occasion_date - today).days if j.occasion_date else None
        nearest = min(d for d in (days_due, days_occ) if d is not None)
        if nearest > horizon_days:
            continue
        holders = [
            {"karigarId": str(kid), "code": names.get(kid, ("?", "?"))[0], "name": names.get(kid, ("?", "?"))[1], "fineGoldHeldG": float(h.fine)}
            for kid, h in job_holdings(db, j.id).items()
            if h.net != 0
        ]
        out.append({
            "jobId": str(j.id),
            "code": j.code,
            "title": j.title,
            "status": j.status.value,
            "dueDate": str(j.due_date),
            "daysToDue": days_due,
            "occasionDate": str(j.occasion_date) if j.occasion_date else None,
            "occasionLabel": j.occasion_label,
            "daysToOccasion": days_occ,
            "piecesOrdered": j.pieces,
            "piecesDelivered": delivered_pieces,
            "headKarigarId": str(j.head_karigar_id) if j.head_karigar_id else None,
            "currentHolders": holders,
        })
    return sorted(out, key=lambda r: min(x for x in (r["daysToDue"], r["daysToOccasion"]) if x is not None))


def payment_delays(db: Session, org_id: uuid.UUID, min_days: int = 0) -> list[dict[str, Any]]:
    """Jeweller-approved settlements the karigar has not been paid for yet, longest wait first."""
    now = utcnow()
    names = {k.id: (k.code, k.name) for k in db.scalars(select(Karigar).where(Karigar.organisation_id == org_id))}
    rows = []
    for s in db.scalars(select(SettlementWorksheet).where(SettlementWorksheet.organisation_id == org_id, SettlementWorksheet.status.in_(AWAITING_PAYMENT))):
        if not s.approved_at:
            continue
        days = (now - _aware(s.approved_at)).days
        if days < min_days:
            continue
        rows.append({
            "worksheetId": str(s.id),
            "code": s.code,
            "status": s.status.value,
            "jobId": str(s.job_id),
            "karigarId": str(s.karigar_id),
            "karigarCode": names.get(s.karigar_id, ("?", "?"))[0],
            "karigarName": names.get(s.karigar_id, ("?", "?"))[1],
            "netPayable": float(s.net_payable_amount),
            "daysSinceApproval": days,
            "disputeReason": s.dispute_reason,
        })
    return sorted(rows, key=lambda r: -r["daysSinceApproval"])
