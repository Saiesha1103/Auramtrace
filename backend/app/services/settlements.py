"""Settlement rules and commercial worksheet calculation service.

Enforces:
  * Deterministic commercial calculations
  * Versioned settlement rules with effective dates
  * Separate tracking of labour compensation and excess gold loss recovery
  * Mandatory human authorization (AI Assistant cannot approve settlements)
  * Immutable audit logging for drafts, submissions, approvals, and rejections
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, Conflict, NotFound
from ..models import (
    JobOrder,
    JobStatus,
    Karigar,
    MaterialReturn,
    ReconciliationRun,
    ReconciliationStatus,
    ReturnCategory,
    SettlementRule,
    SettlementStatus,
    SettlementWorksheet,
    User,
    UserRole,
)
from ..models.base import utcnow
from ..schemas import (
    SettlementApproveRequest,
    SettlementRejectRequest,
    SettlementRuleCreate,
    SettlementWorksheetCreate,
)
from . import audit
from .codes import ensure_unique_code, next_code
from .custody import get_in_org
from .fine_gold import GRAM, ZERO


def create_settlement_rule(db: Session, user: User, req: SettlementRuleCreate) -> SettlementRule:
    org = user.organisation_id
    code = ensure_unique_code(db, SettlementRule, org, req.code) if req.code else next_code(db, SettlementRule, org, "SR")
    rule = SettlementRule(
        organisation_id=org,
        code=code,
        name=req.name,
        karat=req.karat,
        labour_rate_per_g=req.labour_rate_per_g,
        loss_allowance_pct=req.loss_allowance_pct,
        gold_rate_per_fine_g=req.gold_rate_per_fine_g,
        effective_from=req.effective_from,
        effective_to=req.effective_to,
        is_active=True,
        version=1,
    )
    db.add(rule)
    db.flush()
    audit.record(
        db,
        user,
        org,
        "settlement.rule_created",
        "settlement_rule",
        rule.id,
        {"code": code, "name": req.name, "labourRate": float(req.labour_rate_per_g), "goldRate": float(req.gold_rate_per_fine_g)},
    )
    return rule


def list_settlement_rules(db: Session, org_id: uuid.UUID) -> list[SettlementRule]:
    return list(db.scalars(select(SettlementRule).where(SettlementRule.organisation_id == org_id).order_by(SettlementRule.created_at.desc())))


def generate_settlement_worksheet(db: Session, user: User, req: SettlementWorksheetCreate) -> SettlementWorksheet:
    org = user.organisation_id
    job = get_in_org(db, JobOrder, org, req.job_id, "Job")

    # Reconciliation check: job must have a verified reconciliation run
    recon = db.scalar(
        select(ReconciliationRun).where(
            ReconciliationRun.organisation_id == org,
            ReconciliationRun.job_id == job.id,
            ReconciliationRun.is_latest == True,
        )
    )
    if not recon:
        raise BusinessRuleViolation(f"Job {job.code} has not been reconciled yet; run reconciliation first", code="reconciliation_required")

    # Karigar determination: specified or job's head karigar
    karigar_id = req.karigar_id or job.head_karigar_id
    if not karigar_id:
        raise BusinessRuleViolation("A responsible karigar must be assigned to the job or specified in worksheet", code="karigar_required")
    karigar = get_in_org(db, Karigar, org, karigar_id, "Karigar")

    # Settlement rule lookup: explicit or active default
    rule = None
    if req.settlement_rule_id:
        rule = get_in_org(db, SettlementRule, org, req.settlement_rule_id, "Settlement rule")
    else:
        rule = db.scalar(
            select(SettlementRule)
            .where(SettlementRule.organisation_id == org, SettlementRule.is_active == True)
            .order_by(SettlementRule.created_at.desc())
        )

    # Rates: from rule if found, else reasonable defaults (₹450/g labour, ₹7850/g gold rate)
    labour_rate = rule.labour_rate_per_g if rule else Decimal("450.000")
    gold_rate = rule.gold_rate_per_fine_g if rule else Decimal("7850.000")

    # Finished jewellery calculation
    finished_returns = list(
        db.scalars(
            select(MaterialReturn).where(
                MaterialReturn.organisation_id == org,
                MaterialReturn.job_id == job.id,
                MaterialReturn.return_category == ReturnCategory.finished_jewellery,
            )
        )
    )
    finished_gross = sum((r.gross_weight_g for r in finished_returns), ZERO).quantize(GRAM)
    finished_fine = sum((r.fine_gold_g for r in finished_returns), ZERO).quantize(GRAM)

    labour_amount = (finished_gross * labour_rate).quantize(GRAM)

    # Wastage and excess loss recovery calculation
    wastage_allowance_fine = recon.loss_allowance_fine_g
    actual_loss_fine = recon.unexplained_variance_fine_g

    excess_loss_fine = max(ZERO, (actual_loss_fine - wastage_allowance_fine)).quantize(GRAM)
    gold_recovery_amount = (excess_loss_fine * gold_rate).quantize(GRAM)

    approved_deductions = req.approved_deductions or ZERO
    net_payable = (labour_amount - gold_recovery_amount - approved_deductions).quantize(GRAM)

    code = next_code(db, SettlementWorksheet, org, "SW")
    worksheet = SettlementWorksheet(
        organisation_id=org,
        code=code,
        job_id=job.id,
        karigar_id=karigar.id,
        settlement_rule_id=rule.id if rule else None,
        reconciliation_run_id=recon.id,
        status=SettlementStatus.draft,
        finished_gross_g=finished_gross,
        finished_fine_g=finished_fine,
        labour_rate_applied=labour_rate,
        labour_amount=labour_amount,
        wastage_allowance_fine_g=wastage_allowance_fine,
        actual_loss_fine_g=actual_loss_fine,
        excess_loss_fine_g=excess_loss_fine,
        gold_rate_applied=gold_rate,
        gold_recovery_amount=gold_recovery_amount,
        approved_deductions=approved_deductions,
        net_payable_amount=net_payable,
        notes=req.notes,
        created_by_id=user.id,
    )
    db.add(worksheet)
    db.flush()

    audit.record(
        db,
        user,
        org,
        "settlement.worksheet_created",
        "settlement_worksheet",
        worksheet.id,
        {
            "code": code,
            "jobCode": job.code,
            "karigarCode": karigar.code,
            "labourAmount": float(labour_amount),
            "recoveryAmount": float(gold_recovery_amount),
            "netPayable": float(net_payable),
        },
    )
    return worksheet


def submit_settlement_worksheet(db: Session, user: User, worksheet: SettlementWorksheet) -> SettlementWorksheet:
    if worksheet.status != SettlementStatus.draft:
        raise BusinessRuleViolation(f"Cannot submit worksheet in status '{worksheet.status.value}'", code="invalid_status")
    worksheet.status = SettlementStatus.submitted
    worksheet.submitted_by_id = user.id
    worksheet.submitted_at = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        worksheet.organisation_id,
        "settlement.worksheet_submitted",
        "settlement_worksheet",
        worksheet.id,
        {"code": worksheet.code},
    )
    return worksheet


def approve_settlement_worksheet(db: Session, user: User, worksheet: SettlementWorksheet, req: SettlementApproveRequest) -> SettlementWorksheet:
    # Authorization check: only admin or manager can approve
    if user.role not in (UserRole.admin, UserRole.manager):
        raise BusinessRuleViolation("Only an authorized Admin or Manager can approve commercial settlements", code="unauthorized_approval")
    if worksheet.status not in (SettlementStatus.draft, SettlementStatus.submitted):
        raise BusinessRuleViolation(f"Worksheet in status '{worksheet.status.value}' cannot be approved", code="invalid_status")

    worksheet.status = SettlementStatus.approved
    worksheet.approved_by_id = user.id
    worksheet.approved_at = utcnow()
    if req.notes:
        worksheet.notes = f"{worksheet.notes or ''}\nApproval notes: {req.notes}".strip()

    job = db.get(JobOrder, worksheet.job_id)
    if job:
        job.status = JobStatus.settled

    db.flush()
    audit.record(
        db,
        user,
        worksheet.organisation_id,
        "settlement.worksheet_approved",
        "settlement_worksheet",
        worksheet.id,
        {"code": worksheet.code, "approverEmail": user.email, "netPayable": float(worksheet.net_payable_amount)},
    )
    return worksheet


def reject_settlement_worksheet(db: Session, user: User, worksheet: SettlementWorksheet, req: SettlementRejectRequest) -> SettlementWorksheet:
    if user.role not in (UserRole.admin, UserRole.manager):
        raise BusinessRuleViolation("Only an Admin or Manager can reject settlements", code="unauthorized_rejection")
    if worksheet.status not in (SettlementStatus.draft, SettlementStatus.submitted):
        raise BusinessRuleViolation(f"Worksheet in status '{worksheet.status.value}' cannot be rejected", code="invalid_status")

    worksheet.status = SettlementStatus.rejected
    worksheet.rejection_reason = req.reason
    db.flush()
    audit.record(
        db,
        user,
        worksheet.organisation_id,
        "settlement.worksheet_rejected",
        "settlement_worksheet",
        worksheet.id,
        {"code": worksheet.code, "reason": req.reason},
    )
    return worksheet


def list_settlement_worksheets(db: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, karigar_id: uuid.UUID | None = None) -> list[SettlementWorksheet]:
    stmt = select(SettlementWorksheet).where(SettlementWorksheet.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(SettlementWorksheet.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(SettlementWorksheet.karigar_id == karigar_id)
    return list(db.scalars(stmt.order_by(SettlementWorksheet.created_at.desc())))
