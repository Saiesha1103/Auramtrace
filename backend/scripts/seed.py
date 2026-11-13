"""Seed SYNTHETIC development data (mirrors the frontend demo dataset).

    python -m scripts.seed            # into AURUM_DATABASE_URL (run `alembic upgrade head` first)

Everything here is invented for development. The demo logins below are synthetic,
development-only credentials — never use them in a shared or production environment.
Data is written through the same service functions the API uses, so every seeded row
obeys the custody rules (append-only events, balance checks, audit trail).
"""

import sys
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from app import models  # noqa: F401
from app.database import get_sessionmaker
from app.models import (
    ExceptionCase,
    ExceptionStatus,
    ExceptionType,
    JobOrder,
    JobStatus,
    Karat,
    Karigar,
    KarigarKind,
    MaterialReturn,
    Organisation,
    ReconciliationRun,
    ReturnCategory,
    SettlementRule,
    SettlementStatus,
    SettlementWorksheet,
    User,
    UserRole,
)
from app.schemas import (
    AcknowledgeRequest,
    IssueRequest,
    LotCreate,
    MaterialReturnAssayUpdate,
    MaterialReturnCreate,
    MeasurementIn,
    ProductionEntryCreate,
    ProductionMeasurementCreate,
    SettlementApproveRequest,
    SettlementRuleCreate,
    SettlementWorksheetCreate,
    TransferAcknowledgeRequest,
    TransferCreate,
    TransferReverseRequest,
)
from app.services import (
    ai_investigation,
    audit,
    custody,
    exceptions,
    production,
    reconciliation,
    returns,
    settlements,
    transfers,
)
from app.services.security import hash_password

ORG_NAME = "Demo Jewellers (synthetic data)"
DEMO_PASSWORD = "Auram-Demo-2026!"  # synthetic, development only
USERS = [
    ("admin@aurumtrace-demo.example.com", "Demo Admin", UserRole.admin),
    ("manager@aurumtrace-demo.example.com", "Production Manager (demo)", UserRole.manager),
    ("vault@aurumtrace-demo.example.com", "Vault Desk (demo)", UserRole.vault_operator),
    ("viewer@aurumtrace-demo.example.com", "Auditor (demo, read-only)", UserRole.viewer),
]

# code, name, kind, head code, unit, skills
KARIGARS = [
    ("K-01", "Mahesh Soni", KarigarKind.head_karigar, None, "Unit A · Zaveri Bazaar", ["Casting", "Bangles"]),
    ("K-02", "Farida Shaikh", KarigarKind.head_karigar, None, "Unit B · Kalbadevi", ["Temple work", "Chains"]),
    ("K-03", "Ravi Kumar", KarigarKind.karigar, "K-01", "Unit A · Zaveri Bazaar", ["Alloying", "Casting", "Filing"]),
    ("K-05", "Suresh Pal", KarigarKind.karigar, "K-01", "Unit A · Zaveri Bazaar", ["Stone setting", "Polishing"]),
    ("K-07", "Anil Verma", KarigarKind.karigar, "K-02", "Unit B · Kalbadevi", ["Bangles", "Temple work"]),
    ("K-08", "Kavita Jadhav", KarigarKind.karigar, "K-02", "Unit B · Kalbadevi", ["Chains", "Polishing"]),
    ("S-01", "Shree Casting Works", KarigarKind.subcontractor, "K-01", "Andheri East", ["Lost-wax casting"]),
    ("S-03", "Om Polish & Finish", KarigarKind.subcontractor, "K-02", "Bhuleshwar", ["Finishing"]),
]

# code, title, karat, pieces, gross/piece, allowance %, head, due
JOBS = [
    ("J-1160", "Antique jhumka pairs", Karat.k22, 12, "3.6", "1.0", "K-01", date(2026, 11, 1)),
    ("J-1168", "Kada bracelets", Karat.k22, 4, "13.2", "1.5", "K-01", date(2026, 11, 10)),
    ("J-1175", "Mangalsutra pendants", Karat.k18, 10, "2.6", "0.8", "K-01", date(2026, 11, 8)),
    ("J-1182", "Temple bangles", Karat.k22, 6, "5.2", "1.2", "K-02", date(2026, 11, 12)),
    ("J-1186", "Solitaire ring mounts", Karat.k18, 20, "1.6", "1.0", "K-01", date(2026, 11, 25)),
    ("J-1190", "Rope chain 22in", Karat.k22, 3, "20", "1.2", "K-02", date(2026, 11, 20)),
    ("J-1191", "Coin pendants", Karat.k24, 30, "1.0", "0.5", "K-02", date(2026, 11, 18)),
    ("J-1194", "Nose pins", Karat.k18, 40, "0.4", "1.0", "K-02", date(2026, 12, 5)),
]

# lot code, source bar, gross=net, job, issued to, issue date, acknowledged
LOTS = [
    ("L-3279", "Bar 995 · B-778", "40.201", "J-1160", "K-01", date(2026, 10, 21), True),
    ("L-3288", "Bar 995 · B-781", "20.101", "J-1175", "K-01", date(2026, 10, 25), True),
    ("L-3295", "Bar 995 · B-790", "50.251", "J-1168", "K-01", date(2026, 11, 4), True),
    ("L-3301", "Bar 995 · B-792", "30.151", "J-1182", "K-02", date(2026, 11, 2), True),
    ("L-3306", "Bar 995 · B-795", "60.302", "J-1190", "K-02", date(2026, 11, 5), True),
    ("L-3310", "Bar 995 · B-797", "25.126", "J-1186", "K-01", date(2026, 11, 9), False),  # awaiting acknowledgement
    ("L-3312", "Bar 995 · B-798", "30.151", "J-1191", "K-02", date(2026, 11, 10), True),
]


def at(d: date, hour: int = 10) -> datetime:
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=UTC)


def main() -> int:
    db = get_sessionmaker()()
    existing_org = db.scalar(select(Organisation).where(Organisation.name == ORG_NAME))
    if existing_org:
        # Check if Phase 2 is already seeded
        has_phase2 = db.scalar(select(ReconciliationRun).where(ReconciliationRun.organisation_id == existing_org.id))
        if has_phase2:
            print(f"'{ORG_NAME}' already fully seeded (Phase 1 + Phase 2) - nothing to do.")
            return 0
        org = existing_org
    else:
        org = Organisation(name=ORG_NAME)
        db.add(org)
        db.flush()

    # Users
    users = {}
    for email, name, role in USERS:
        u = db.scalar(select(User).where(User.organisation_id == org.id, User.email == email))
        if not u:
            u = User(organisation_id=org.id, email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            db.flush()
        users[role] = u

    admin, manager, vault = users[UserRole.admin], users[UserRole.manager], users[UserRole.vault_operator]
    audit.record(db, admin, org.id, "organisation.seeded", "organisation", org.id, {"note": "synthetic development data"})

    # Karigars
    kar: dict[str, Karigar] = {}
    for code, name, kind, head, unit, skills in KARIGARS:
        k = db.scalar(select(Karigar).where(Karigar.organisation_id == org.id, Karigar.code == code))
        if not k:
            k = Karigar(organisation_id=org.id, code=code, name=name, kind=kind, head_karigar_id=kar[head].id if head else None, unit=unit, skills=skills)
            db.add(k)
            db.flush()
        kar[code] = k

    # Jobs
    jobs: dict[str, JobOrder] = {}
    for code, title, karat, pieces, gpp, allow, head, due in JOBS:
        j = db.scalar(select(JobOrder).where(JobOrder.organisation_id == org.id, JobOrder.code == code))
        if not j:
            j = JobOrder(
                organisation_id=org.id,
                code=code,
                title=title,
                karat=karat,
                target_fineness_ppt={Karat.k24: Decimal("995"), Karat.k22: Decimal("916"), Karat.k18: Decimal("750")}[karat],
                pieces=pieces,
                target_gross_per_piece_g=Decimal(gpp),
                loss_allowance_pct=Decimal(allow),
                head_karigar_id=kar[head].id,
                due_date=due,
                status=JobStatus.draft,
                created_by_id=admin.id,
                contract_version="KC-2026.1",
            )
            db.add(j)
            db.flush()
        jobs[code] = j

    # Lots & Issuances
    meas = MeasurementIn(scale_id="SC-01", operator_name="Vault desk", method="manual")
    lots = {}
    for code, source, weight, job_code, to, day, acked in LOTS:
        lot = db.scalar(select(models.MaterialLot).where(models.MaterialLot.organisation_id == org.id, models.MaterialLot.code == code))
        if not lot:
            lot = custody.create_lot(
                db,
                vault,
                LotCreate(code=code, source=source, gross_weight_g=Decimal(weight), net_weight_g=Decimal(weight), fineness_ppt=Decimal("995"), measurement=meas, occurred_at=at(day, 9)),
            )
            ev = custody.issue(
                db,
                vault,
                lot,
                IssueRequest(job_id=jobs[job_code].id, karigar_id=kar[to].id, gross_weight_g=Decimal(weight), net_weight_g=Decimal(weight), measurement=meas, challan_ref=f"JWC-26-{code[2:]}", occurred_at=at(day, 10)),
            )
            if acked:
                custody.acknowledge(db, vault, ev, AcknowledgeRequest(acknowledged_by_name=kar[to].name, evidence_ref=f"ACK-{code[2:]}", occurred_at=at(day, 11)))
        lots[code] = lot

    # =========================================================================
    # PHASE 2: RICH PRODUCTION, TRANSFERS, RETURNS, RECONCILIATION & AI DEMO
    # =========================================================================

    # 1. Multi-level Subcontracting Transfers for J-1160 (Antique Jhumka Pairs)
    # Head K-01 transfers 15.000 g to Karigar K-03 (Ravi Kumar)
    t1 = transfers.create_transfer(
        db,
        manager,
        TransferCreate(
            job_id=jobs["J-1160"].id,
            from_karigar_id=kar["K-01"].id,
            to_karigar_id=kar["K-03"].id,
            lot_id=lots["L-3279"].id,
            gross_weight_g=Decimal("15.000"),
            net_weight_g=Decimal("15.000"),
            measurement=meas,
            challan_ref="CH-TR-1160-01",
        ),
    )
    transfers.acknowledge_transfer(
        db,
        manager,
        t1,
        TransferAcknowledgeRequest(acknowledged_by_name=kar["K-03"].name, evidence_ref="ACK-TR-01"),
    )

    # 2. Multi-level Transfers for J-1168 (Kada Bracelets): Head -> Subcontractor -> Karigar
    t2 = transfers.create_transfer(
        db,
        manager,
        TransferCreate(
            job_id=jobs["J-1168"].id,
            from_karigar_id=kar["K-01"].id,
            to_karigar_id=kar["S-01"].id,
            lot_id=lots["L-3295"].id,
            gross_weight_g=Decimal("20.000"),
            net_weight_g=Decimal("20.000"),
            measurement=meas,
            challan_ref="CH-TR-1168-SUB",
        ),
    )
    transfers.acknowledge_transfer(
        db,
        manager,
        t2,
        TransferAcknowledgeRequest(acknowledged_by_name="Shree Casting Rep", evidence_ref="ACK-SUB-01"),
    )

    # Reversal Demo: Temporary transfer from K-01 to K-05, immediately reversed
    t_rev = transfers.create_transfer(
        db,
        manager,
        TransferCreate(
            job_id=jobs["J-1168"].id,
            from_karigar_id=kar["K-01"].id,
            to_karigar_id=kar["K-05"].id,
            lot_id=lots["L-3295"].id,
            gross_weight_g=Decimal("5.000"),
            net_weight_g=Decimal("5.000"),
            measurement=meas,
            challan_ref="CH-TR-REV-01",
        ),
    )
    transfers.reverse_transfer(
        db,
        manager,
        t_rev,
        TransferReverseRequest(reason="Transfer created in error; material re-routed to casting master.", notes="Reversed via compensating event"),
    )

    # 3. Unacknowledged Transfer for J-1182 (Temple Bangles)
    # Head K-02 transfers 10.000 g to K-07 (Anil Verma) — intentionally NOT acknowledged
    transfers.create_transfer(
        db,
        manager,
        TransferCreate(
            job_id=jobs["J-1182"].id,
            from_karigar_id=kar["K-02"].id,
            to_karigar_id=kar["K-07"].id,
            lot_id=lots["L-3301"].id,
            gross_weight_g=Decimal("10.000"),
            net_weight_g=Decimal("10.000"),
            measurement=meas,
            challan_ref="CH-TR-1182-UNACK",
        ),
    )

    # 4. Production Entries & Measurements for J-1160
    p_entry = production.create_production_entry(
        db,
        manager,
        ProductionEntryCreate(
            job_id=jobs["J-1160"].id,
            karigar_id=kar["K-03"].id,
            stage="Casting & Filing",
            input_gross_weight_g=Decimal("15.000"),
            input_net_metal_weight_g=Decimal("15.000"),
            fineness_ppt=Decimal("916.0"),
            notes="Lost wax casting completed for jhumka filigree components",
        ),
    )
    production.create_production_measurement(
        db,
        manager,
        ProductionMeasurementCreate(
            job_id=jobs["J-1160"].id,
            karigar_id=kar["K-03"].id,
            stage="Casting & Filing",
            input_gross_weight_g=Decimal("15.000"),
            input_net_metal_weight_g=Decimal("15.000"),
            output_gross_weight_g=Decimal("14.880"),
            output_net_metal_weight_g=Decimal("14.880"),
            fineness_ppt=Decimal("916.0"),
            pieces=12,
            notes="Filigree sprue removal and fine bench filing",
        ),
    )
    production.complete_production_entry(
        db,
        manager,
        p_entry,
    )

    # 5. Returns
    # J-1160: Clean finished return (with pearls/stones) + scrap -> Fully Reconciled within allowance
    returns.create_return(
        db,
        manager,
        MaterialReturnCreate(
            job_id=jobs["J-1160"].id,
            karigar_id=kar["K-03"].id,
            lot_id=lots["L-3279"].id,
            return_category=ReturnCategory.finished_jewellery,
            gross_weight_g=Decimal("16.800"),  # contains 2.000 g pearls/stones
            net_metal_weight_g=Decimal("14.800"),
            stone_weight_g=Decimal("2.000"),
            declared_fineness_ppt=Decimal("995.0"),
            pieces=12,
            is_partial=True,
            measurement=meas,
            challan_ref="RET-1160-FG",
        ),
    )
    returns.create_return(
        db,
        manager,
        MaterialReturnCreate(
            job_id=jobs["J-1160"].id,
            karigar_id=kar["K-01"].id,
            lot_id=lots["L-3279"].id,
            return_category=ReturnCategory.scrap,
            gross_weight_g=Decimal("25.100"),
            net_metal_weight_g=Decimal("25.100"),
            declared_fineness_ppt=Decimal("995.0"),
            pieces=1,
            is_partial=False,
            retained_scrap_g=Decimal("0.100"),  # Workshop retained scrap
            measurement=meas,
            challan_ref="RET-1160-SCRAP",
        ),
    )

    # J-1168: Deficit return (Karigar K-01 held 30.251 g, returns 25.000 g -> 5.251 g discrepancy!)
    returns.create_return(
        db,
        manager,
        MaterialReturnCreate(
            job_id=jobs["J-1168"].id,
            karigar_id=kar["K-01"].id,
            lot_id=lots["L-3295"].id,
            return_category=ReturnCategory.finished_jewellery,
            gross_weight_g=Decimal("25.000"),
            net_metal_weight_g=Decimal("25.000"),
            declared_fineness_ppt=Decimal("995.0"),
            pieces=4,
            is_partial=False,
            measurement=meas,
            challan_ref="RET-1168-DEFICIT",
        ),
    )

    # J-1175: Purity Shortfall Return (declared 995 ppt, assayed 965 ppt -> 30 ppt shortfall)
    returns.create_return(
        db,
        manager,
        MaterialReturnCreate(
            job_id=jobs["J-1175"].id,
            karigar_id=kar["K-01"].id,
            lot_id=lots["L-3288"].id,
            return_category=ReturnCategory.finished_jewellery,
            gross_weight_g=Decimal("20.000"),
            net_metal_weight_g=Decimal("20.000"),
            declared_fineness_ppt=Decimal("995.0"),
            assayed_fineness_ppt=Decimal("965.0"),
            pieces=10,
            is_partial=False,
            measurement=meas,
            assay_evidence_ref="CERT-HALLMARK-7701",
            notes="Refinery fire assay discovered 30 ppt purity shortfall",
            challan_ref="RET-1175-PURITY",
        ),
    )

    # 6. Reconciliations
    # J-1160: Reconcile within allowance
    reconciliation.run_reconciliation(db, manager, jobs["J-1160"])
    jobs["J-1160"].status = JobStatus.reconciled

    # J-1168: Reconcile with excess variance
    reconciliation.run_reconciliation(db, manager, jobs["J-1168"])

    # J-1175: Reconcile with fineness mismatch
    reconciliation.run_reconciliation(db, manager, jobs["J-1175"])

    # J-1182: Reconcile with unacknowledged transfer
    reconciliation.run_reconciliation(db, manager, jobs["J-1182"])

    # 7. Automated Exception Detection
    exceptions.detect_exceptions_for_job(db, manager, jobs["J-1168"])
    exceptions.detect_exceptions_for_job(db, manager, jobs["J-1175"])
    exceptions.detect_exceptions_for_job(db, manager, jobs["J-1182"])

    # Find the variance exception on J-1168
    ex_cases = exceptions.list_exceptions(db, org.id, job_id=jobs["J-1168"].id)
    if ex_cases:
        target_ex = ex_cases[0]
        # Assign investigator
        exceptions.assign_investigator(db, manager, target_ex, manager.id)
        exceptions.add_investigation_notes(
            db,
            manager,
            target_ex,
            "Physical search conducted at subcontractor unit S-01. Vacuum dust collector bags sent for refining.",
        )
        exceptions.add_exception_evidence(
            db,
            manager,
            target_ex,
            evidence_type="vacuum_dust_sweep",
            title="S-01 Workshop Bench Sweep Manifest",
            file_url="https://vault.example.com/evidence/sweep-1168.pdf",
            details={"refiningEstimateG": 4.800, "recoveryLocation": "Andheri East"},
        )
        # 8. Run AI Investigation Assistant
        ai_investigation.run_investigation(db, manager, target_ex.id)

    # Find the purity mismatch exception on J-1175 and resolve it
    purity_cases = exceptions.list_exceptions(db, org.id, job_id=jobs["J-1175"].id)
    if purity_cases:
        p_ex = purity_cases[0]
        exceptions.resolve_exception(
            db,
            manager,
            p_ex,
            resolution_notes="Commercial penalty deduction of 0.600 g fine gold agreed with Mahesh Soni and applied to monthly settlement worksheet.",
        )

    # 9. Settlement Rules & Commercial Worksheets
    s_rule = settlements.create_settlement_rule(
        db,
        admin,
        SettlementRuleCreate(
            code="SR-22K-STD",
            name="Master Karigar Standard Commercial Agreement",
            karat=Karat.k22,
            labour_rate_per_g=Decimal("450.000"),
            loss_allowance_pct=Decimal("1.0"),
            gold_rate_per_fine_g=Decimal("7450.000"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
        ),
    )

    # Generate Settlement Worksheet for J-1160
    ws1 = settlements.generate_settlement_worksheet(
        db,
        manager,
        SettlementWorksheetCreate(
            job_id=jobs["J-1160"].id,
            karigar_id=kar["K-01"].id,
            settlement_rule_id=s_rule.id,
            notes="Final settlement for completed Antique Jhumka Pairs batch.",
        ),
    )
    settlements.submit_settlement_worksheet(db, manager, ws1)
    settlements.approve_settlement_worksheet(db, admin, ws1, SettlementApproveRequest(notes="Approved for treasury disbursement"))
    jobs["J-1160"].status = JobStatus.settled

    db.commit()
    print(f"Seeded '{ORG_NAME}' with comprehensive Phase 1 & Phase 2 data:")
    print(f"  - {len(USERS)} users, {len(KARIGARS)} karigars, {len(JOBS)} jobs, {len(LOTS)} lots")
    print(f"  - Multi-level transfers (with acknowledgements, reversals, and unacknowledged transfers)")
    print(f"  - Production entries & measurements across manufacturing stages")
    print(f"  - Finished jewellery, scrap, and assay shortfall returns")
    print(f"  - 4 Reconciled jobs: within allowance, above allowance, fineness mismatch, unacknowledged transfer")
    print(f"  - Exception lifecycle: open, investigating, resolved, with AI investigation run and evidence links")
    print(f"  - Commercial settlement rules and approved settlement worksheet for J-1160")
    print("Demo logins: see USERS / DEMO_PASSWORD in scripts/seed.py (synthetic, development only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
