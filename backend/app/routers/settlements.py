"""Settlement rules, commercial worksheets, and human approval workflow."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager
from ..errors import NotFound
from ..models import (
    SettlementRule,
    SettlementWorksheet,
)
from ..schemas import (
    ERROR_RESPONSES,
    Page,
    SettlementApproveRequest,
    SettlementRejectRequest,
    SettlementRuleCreate,
    SettlementRuleOut,
    SettlementWorksheetCreate,
    SettlementWorksheetOut,
)
from ..services.custody import get_in_org
from ..services.settlements import (
    approve_settlement_worksheet,
    create_settlement_rule,
    generate_settlement_worksheet,
    list_settlement_rules,
    list_settlement_worksheets,
    reject_settlement_worksheet,
    submit_settlement_worksheet,
)

router = APIRouter(prefix="/settlements", tags=["settlement"])


def _to_rule_out(r: SettlementRule) -> SettlementRuleOut:
    return SettlementRuleOut(
        id=r.id,
        code=r.code,
        name=r.name,
        karat=r.karat,
        labour_rate_per_g=r.labour_rate_per_g,
        loss_allowance_pct=r.loss_allowance_pct,
        gold_rate_per_fine_g=r.gold_rate_per_fine_g,
        effective_from=r.effective_from,
        effective_to=r.effective_to,
        is_active=r.is_active,
        version=r.version,
        created_at=r.created_at,
    )


def _to_sheet_out(w: SettlementWorksheet) -> SettlementWorksheetOut:
    return SettlementWorksheetOut(
        id=w.id,
        code=w.code,
        job_id=w.job_id,
        karigar_id=w.karigar_id,
        settlement_rule_id=w.settlement_rule_id,
        reconciliation_run_id=w.reconciliation_run_id,
        status=w.status,
        finished_gross_g=w.finished_gross_g,
        finished_fine_g=w.finished_fine_g,
        labour_rate_applied=w.labour_rate_applied,
        labour_amount=w.labour_amount,
        wastage_allowance_fine_g=w.wastage_allowance_fine_g,
        actual_loss_fine_g=w.actual_loss_fine_g,
        excess_loss_fine_g=w.excess_loss_fine_g,
        gold_rate_applied=w.gold_rate_applied,
        gold_recovery_amount=w.gold_recovery_amount,
        approved_deductions=w.approved_deductions,
        net_payable_amount=w.net_payable_amount,
        notes=w.notes,
        rejection_reason=w.rejection_reason,
        submitted_at=w.submitted_at,
        approved_at=w.approved_at,
        created_at=w.created_at,
    )


@router.post("/rules", response_model=SettlementRuleOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_rule(req: SettlementRuleCreate, db: DB, user: Manager):
    """Create a versioned commercial settlement rule with effective dates."""
    rule = create_settlement_rule(db, user, req)
    db.commit()
    return _to_rule_out(rule)


@router.get("/rules", response_model=list[SettlementRuleOut], responses=ERROR_RESPONSES)
def get_rules(db: DB, user: CurrentUser):
    rules = list_settlement_rules(db, user.organisation_id)
    return [_to_rule_out(r) for r in rules]


@router.post("/worksheets", response_model=SettlementWorksheetOut, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES)
def post_worksheet(req: SettlementWorksheetCreate, db: DB, user: Manager):
    """Generate a draft commercial settlement worksheet based on fine-gold reconciliation."""
    sheet = generate_settlement_worksheet(db, user, req)
    db.commit()
    return _to_sheet_out(sheet)


@router.get("/worksheets", response_model=Page[SettlementWorksheetOut], responses=ERROR_RESPONSES)
def get_worksheets(
    db: DB,
    user: CurrentUser,
    job_id: uuid.UUID | None = Query(None, alias="jobId"),
    karigar_id: uuid.UUID | None = Query(None, alias="karigarId"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(SettlementWorksheet).where(SettlementWorksheet.organisation_id == user.organisation_id)
    if job_id:
        stmt = stmt.where(SettlementWorksheet.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(SettlementWorksheet.karigar_id == karigar_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(SettlementWorksheet.created_at.desc()).limit(limit).offset(offset)))
    return Page(items=[_to_sheet_out(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/worksheets/{id}", response_model=SettlementWorksheetOut, responses=ERROR_RESPONSES)
def get_worksheet_by_id(id: uuid.UUID, db: DB, user: CurrentUser):
    sheet = get_in_org(db, SettlementWorksheet, user.organisation_id, id, "Settlement worksheet")
    return _to_sheet_out(sheet)


@router.post("/worksheets/{id}/submit", response_model=SettlementWorksheetOut, responses=ERROR_RESPONSES)
def post_submit_worksheet(id: uuid.UUID, db: DB, user: Manager):
    sheet = get_in_org(db, SettlementWorksheet, user.organisation_id, id, "Settlement worksheet")
    submitted = submit_settlement_worksheet(db, user, sheet)
    db.commit()
    return _to_sheet_out(submitted)


@router.post("/worksheets/{id}/approve", response_model=SettlementWorksheetOut, responses=ERROR_RESPONSES)
def post_approve_worksheet(id: uuid.UUID, req: SettlementApproveRequest, db: DB, user: Manager):
    """Authorized human approval of settlement. Sets job status to settled."""
    sheet = get_in_org(db, SettlementWorksheet, user.organisation_id, id, "Settlement worksheet")
    approved = approve_settlement_worksheet(db, user, sheet, req)
    db.commit()
    return _to_sheet_out(approved)


@router.post("/worksheets/{id}/reject", response_model=SettlementWorksheetOut, responses=ERROR_RESPONSES)
def post_reject_worksheet(id: uuid.UUID, req: SettlementRejectRequest, db: DB, user: Manager):
    sheet = get_in_org(db, SettlementWorksheet, user.organisation_id, id, "Settlement worksheet")
    rejected = reject_settlement_worksheet(db, user, sheet, req)
    db.commit()
    return _to_sheet_out(rejected)
