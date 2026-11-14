"""Fine-gold reconciliation engine.

Deterministic, auditable fine-gold reconciliation adhering to PRD §3 & Appendix A:
  Fine Gold Equivalent = Net Metal Weight × Fineness / 1000  (Decimal, 0.001 g precision, half-up)

Reconciliation equation:
  Issued Fine Gold = Finished Jewellery Fine Gold
                   + Returned Scrap Fine Gold
                   + Retained Scrap Fine Gold
                   + Closing WIP Fine Gold
                   + Documented Process Loss
                   + Unexplained Variance

Internal transfers change custody, NOT total metal issued to the job.
Every run produces an immutable, versioned ReconciliationRun snapshot with drillable line items.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    JobOrder,
    JobStatus,
    Karigar,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    MaterialReturn,
    ProductionMeasurement,
    ReconciliationLineItem,
    ReconciliationRun,
    ReconciliationStatus,
    ReturnCategory,
    User,
)
from ..models.base import utcnow
from ..schemas import (
    ReconciliationLineItemOut,
    ReconciliationRunOut,
    ReconciliationSummaryOut,
)
from . import audit
from .custody import get_in_org
from .fine_gold import GRAM, ZERO, fine_gold
from .ledger import followups, job_holdings, job_issued_total, pending_acknowledgements


def run_reconciliation(db: Session, user: User, job: JobOrder) -> ReconciliationRun:
    """Run deterministic reconciliation for a job and persist an immutable snapshot."""
    org = user.organisation_id

    # 1. Total issued metal (issues minus reversed issues)
    issued_holding = job_issued_total(db, job.id)
    issued_gross = issued_holding.gross
    issued_net = issued_holding.net
    issued_fine = issued_holding.fine

    # 2. Query all returns for this job
    returns = list(
        db.scalars(
            select(MaterialReturn)
            .where(MaterialReturn.organisation_id == org, MaterialReturn.job_id == job.id)
            .order_by(MaterialReturn.created_at)
        )
    )

    finished_fine = ZERO
    returned_scrap_fine = ZERO
    retained_scrap_fine = ZERO
    closing_wip_fine = ZERO

    line_items: list[dict[str, Any]] = []

    for r in returns:
        fine = r.fine_gold_g
        if r.return_category == ReturnCategory.finished_jewellery:
            finished_fine = (finished_fine + fine).quantize(GRAM)
            line_items.append({
                "category": "finished_jewellery",
                "karigar_id": r.karigar_id,
                "lot_id": r.lot_id,
                "gross_weight_g": r.gross_weight_g,
                "net_metal_weight_g": r.net_metal_weight_g,
                "fineness_ppt": r.assayed_fineness_ppt or r.declared_fineness_ppt,
                "fine_gold_g": fine,
                "notes": f"Return {r.code}: {r.pieces} pcs finished jewellery",
            })
        elif r.return_category in (ReturnCategory.scrap, ReturnCategory.dust):
            returned_scrap_fine = (returned_scrap_fine + fine).quantize(GRAM)
            line_items.append({
                "category": f"returned_{r.return_category.value}",
                "karigar_id": r.karigar_id,
                "lot_id": r.lot_id,
                "gross_weight_g": r.gross_weight_g,
                "net_metal_weight_g": r.net_metal_weight_g,
                "fineness_ppt": r.assayed_fineness_ppt or r.declared_fineness_ppt,
                "fine_gold_g": fine,
                "notes": f"Return {r.code}: {r.return_category.value}",
            })
        elif r.return_category == ReturnCategory.wip:
            # Explicit WIP return or declared closing WIP
            closing_wip_fine = (closing_wip_fine + fine).quantize(GRAM)
            line_items.append({
                "category": "closing_wip",
                "karigar_id": r.karigar_id,
                "lot_id": r.lot_id,
                "gross_weight_g": r.gross_weight_g,
                "net_metal_weight_g": r.net_metal_weight_g,
                "fineness_ppt": r.assayed_fineness_ppt or r.declared_fineness_ppt,
                "fine_gold_g": fine,
                "notes": f"Return {r.code}: declared WIP return",
            })

        # Check for retained scrap on this return
        if r.retained_scrap_g > 0:
            eff_fineness = r.assayed_fineness_ppt or r.declared_fineness_ppt
            ret_fine = fine_gold(r.retained_scrap_g, eff_fineness)
            retained_scrap_fine = (retained_scrap_fine + ret_fine).quantize(GRAM)
            line_items.append({
                "category": "retained_scrap",
                "karigar_id": r.karigar_id,
                "lot_id": r.lot_id,
                "gross_weight_g": r.retained_scrap_g,
                "net_metal_weight_g": r.retained_scrap_g,
                "fineness_ppt": eff_fineness,
                "fine_gold_g": ret_fine,
                "notes": f"Retained scrap reported on return {r.code}",
            })

    # 4. Documented process loss from production measurements
    measurements = list(
        db.scalars(
            select(ProductionMeasurement)
            .where(ProductionMeasurement.organisation_id == org, ProductionMeasurement.job_id == job.id, ProductionMeasurement.is_superseded == False)
        )
    )
    documented_loss_fine = ZERO

    # 5. Calculate accounting totals
    actual_accounted_fine = (finished_fine + returned_scrap_fine + retained_scrap_fine + closing_wip_fine + documented_loss_fine).quantize(GRAM)
    unexplained_variance_fine = (issued_fine - actual_accounted_fine).quantize(GRAM)

    variance_pct = (
        (unexplained_variance_fine / issued_fine * Decimal("100.0")).quantize(Decimal("0.1"))
        if issued_fine > ZERO
        else Decimal("0.0")
    )
    allowance_fine = (issued_fine * (job.loss_allowance_pct / Decimal("100.0"))).quantize(GRAM)

    # 6. Check pending transfers / acknowledgements (internal karigar transfers)
    job_events = list(
        db.scalars(select(MaterialEvent).where(MaterialEvent.organisation_id == org, MaterialEvent.job_id == job.id))
    )
    transfer_events = [e for e in job_events if e.event_type == MaterialEventType.transfer]
    fu_transfers = followups(db, [e.id for e in transfer_events])
    unack_count = sum(
        1 for e in transfer_events
        if fu_transfers[e.id].reversal_id is None
        and (fu_transfers[e.id].acknowledgement_id is None or fu_transfers[e.id].acknowledgement_reversed)
    )

    # 7. Check for purity mismatches
    purity_mismatch_found = any(
        r.assayed_fineness_ppt is not None and abs(r.declared_fineness_ppt - r.assayed_fineness_ppt) >= Decimal("20.0")
        for r in returns
    )

    # 8. Determine status
    if issued_fine == ZERO:
        status = ReconciliationStatus.pending_reconciliation
    elif unack_count > 0:
        status = ReconciliationStatus.unacknowledged_transfer
    elif purity_mismatch_found:
        status = ReconciliationStatus.fineness_mismatch
    elif unexplained_variance_fine > allowance_fine:
        status = ReconciliationStatus.above_allowance
    elif unexplained_variance_fine > ZERO:
        status = ReconciliationStatus.within_allowance
    else:
        # Variance <= 0 (e.g. within normal limits)
        status = ReconciliationStatus.within_allowance

    # 9. Supporting IDs
    supporting_events = [str(e.id) for e in job_events]
    supporting_returns = [str(r.id) for r in returns]
    supporting_meas = [str(m.id) for m in measurements]

    # 10. Mark previous runs for this job as not latest
    prev_runs = list(db.scalars(select(ReconciliationRun).where(ReconciliationRun.job_id == job.id)))
    for p in prev_runs:
        p.is_latest = False
    run_num = len(prev_runs) + 1

    calc_details = {
        "formula": "Issued Fine = Finished Fine + Returned Scrap Fine + Retained Scrap Fine + Closing WIP + Documented Loss + Variance",
        "lossAllowanceFormula": f"Issued Fine ({float(issued_fine):.3f} g) × {float(job.loss_allowance_pct):.1f}% = {float(allowance_fine):.3f} g",
        "unackEventCount": unack_count,
        "purityMismatchFound": purity_mismatch_found,
        "totalReturnsCount": len(returns),
    }

    recon_run = ReconciliationRun(
        organisation_id=org,
        job_id=job.id,
        run_number=run_num,
        version_identifier=f"REC-{job.code}-v{run_num}",
        status=status,
        total_issued_gross_g=issued_gross,
        total_issued_net_g=issued_net,
        total_issued_fine_g=issued_fine,
        finished_jewellery_fine_g=finished_fine,
        returned_scrap_fine_g=returned_scrap_fine,
        retained_scrap_fine_g=retained_scrap_fine,
        closing_wip_fine_g=closing_wip_fine,
        documented_loss_fine_g=documented_loss_fine,
        expected_fine_g=issued_fine,
        actual_accounted_fine_g=actual_accounted_fine,
        unexplained_variance_fine_g=unexplained_variance_fine,
        variance_pct=variance_pct,
        loss_allowance_pct=job.loss_allowance_pct,
        loss_allowance_fine_g=allowance_fine,
        supporting_event_ids=supporting_events,
        supporting_return_ids=supporting_returns,
        supporting_measurement_ids=supporting_meas,
        calculation_details=calc_details,
        is_latest=True,
        created_by_id=user.id,
    )
    db.add(recon_run)
    db.flush()

    for item in line_items:
        li = ReconciliationLineItem(
            organisation_id=org,
            reconciliation_run_id=recon_run.id,
            category=item["category"],
            karigar_id=item["karigar_id"],
            lot_id=item["lot_id"],
            gross_weight_g=item["gross_weight_g"],
            net_metal_weight_g=item["net_metal_weight_g"],
            fineness_ppt=item["fineness_ppt"],
            fine_gold_g=item["fine_gold_g"],
            notes=item["notes"],
        )
        db.add(li)

    # If within allowance and no closing WIP is open, mark job reconciled
    if status == ReconciliationStatus.within_allowance and closing_wip_fine == ZERO and len(returns) > 0:
        job.status = JobStatus.reconciled

    db.flush()
    audit.record(
        db,
        user,
        org,
        "reconciliation.run_completed",
        "reconciliation_run",
        recon_run.id,
        {
            "jobCode": job.code,
            "runNumber": run_num,
            "status": status.value,
            "issuedFineG": float(issued_fine),
            "accountedFineG": float(actual_accounted_fine),
            "varianceFineG": float(unexplained_variance_fine),
            "allowanceFineG": float(allowance_fine),
        },
    )
    return recon_run


def get_latest_reconciliation(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> ReconciliationRun | None:
    return db.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.organisation_id == org_id,
            ReconciliationRun.job_id == job_id,
            ReconciliationRun.is_latest == True,
        )
    )


def list_reconciliation_runs(db: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None) -> list[ReconciliationRun]:
    stmt = select(ReconciliationRun).where(ReconciliationRun.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(ReconciliationRun.job_id == job_id)
    return list(db.scalars(stmt.order_by(ReconciliationRun.created_at.desc())))


def get_reconciliation_summary(db: Session, org_id: uuid.UUID) -> ReconciliationSummaryOut:
    all_jobs = list(db.scalars(select(JobOrder).where(JobOrder.organisation_id == org_id)))
    latest_runs = list(
        db.scalars(select(ReconciliationRun).where(ReconciliationRun.organisation_id == org_id, ReconciliationRun.is_latest == True))
    )
    reconciled_jobs = sum(1 for j in all_jobs if j.status in (JobStatus.reconciled, JobStatus.settled))
    exception_jobs = sum(
        1 for r in latest_runs if r.status in (ReconciliationStatus.above_allowance, ReconciliationStatus.fineness_mismatch, ReconciliationStatus.unexplained_material_variance)
    )
    open_wip_jobs = sum(1 for r in latest_runs if r.closing_wip_fine_g > ZERO)

    total_issued = sum((r.total_issued_fine_g for r in latest_runs), ZERO).quantize(GRAM)
    total_accounted = sum((r.actual_accounted_fine_g for r in latest_runs), ZERO).quantize(GRAM)
    total_variance = sum((r.unexplained_variance_fine_g for r in latest_runs), ZERO).quantize(GRAM)

    return ReconciliationSummaryOut(
        total_jobs=len(all_jobs),
        reconciled_jobs=reconciled_jobs,
        jobs_with_exceptions=exception_jobs,
        open_wip_jobs=open_wip_jobs,
        total_issued_fine_g=total_issued,
        total_accounted_fine_g=total_accounted,
        total_variance_fine_g=total_variance,
    )
