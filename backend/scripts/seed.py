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
from app.models import JobOrder, JobStatus, Karat, Karigar, KarigarKind, Organisation, User, UserRole
from app.schemas import AcknowledgeRequest, IssueRequest, LotCreate, MeasurementIn
from app.services import audit, custody
from app.services.security import hash_password

ORG_NAME = "Demo Jewellers (synthetic data)"
DEMO_PASSWORD = "Aurum-Demo-2026!"  # synthetic, development only
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
    if db.scalar(select(Organisation).where(Organisation.name == ORG_NAME)):
        print(f"'{ORG_NAME}' already exists - nothing to do (drop the database to reseed).")
        return 0

    org = Organisation(name=ORG_NAME)
    db.add(org)
    db.flush()
    users = {}
    for email, name, role in USERS:
        u = User(organisation_id=org.id, email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        users[role] = u
    db.flush()
    admin, vault = users[UserRole.admin], users[UserRole.vault_operator]
    audit.record(db, admin, org.id, "organisation.seeded", "organisation", org.id, {"note": "synthetic development data"})

    kar: dict[str, Karigar] = {}
    for code, name, kind, head, unit, skills in KARIGARS:
        k = Karigar(organisation_id=org.id, code=code, name=name, kind=kind, head_karigar_id=kar[head].id if head else None, unit=unit, skills=skills)
        db.add(k)
        db.flush()
        kar[code] = k

    jobs: dict[str, JobOrder] = {}
    for code, title, karat, pieces, gpp, allow, head, due in JOBS:
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

    meas = MeasurementIn(scale_id="SC-01", operator_name="Vault desk", method="manual")
    for code, source, weight, job_code, to, day, acked in LOTS:
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

    db.commit()
    print(f"Seeded '{ORG_NAME}': {len(USERS)} users, {len(KARIGARS)} karigars, {len(JOBS)} jobs, {len(LOTS)} lots issued (1 awaiting acknowledgement).")
    print("Demo logins: see USERS / DEMO_PASSWORD in scripts/seed.py (synthetic, development only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
