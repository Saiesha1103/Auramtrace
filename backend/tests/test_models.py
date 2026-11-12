"""Models, relationships and DB-level constraints."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    CustodianType,
    JobOrder,
    Karat,
    Karigar,
    KarigarKind,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    Organisation,
    User,
    UserRole,
)


def _org_user(db):
    org = Organisation(name="Model Test Org")
    db.add(org)
    db.flush()
    u = User(organisation_id=org.id, email=f"{uuid.uuid4().hex[:8]}@example.com", full_name="M", role=UserRole.admin, password_hash="x")
    db.add(u)
    db.flush()
    return org, u


def test_relationships(db):
    org, u = _org_user(db)
    head = Karigar(organisation_id=org.id, code="K-1", name="Head", kind=KarigarKind.head_karigar)
    db.add(head)
    db.flush()
    k = Karigar(organisation_id=org.id, code="K-2", name="Worker", kind=KarigarKind.karigar, head_karigar_id=head.id)
    job = JobOrder(organisation_id=org.id, code="J-1", title="T", karat=Karat.k22, target_fineness_ppt=Decimal("916"), pieces=1, due_date=date(2026, 12, 1), created_by_id=u.id, head_karigar_id=head.id)
    lot = MaterialLot(organisation_id=org.id, code="L-1", gross_weight_g=Decimal("10"), net_weight_g=Decimal("10"), stone_weight_g=Decimal("0"), fineness_ppt=Decimal("995"), fine_gold_g=Decimal("9.950"), created_by_id=u.id)
    db.add_all([k, job, lot])
    db.flush()
    ev = MaterialEvent(organisation_id=org.id, event_type=MaterialEventType.issue, lot_id=lot.id, job_id=job.id, from_type=CustodianType.vault, to_type=CustodianType.karigar, to_karigar_id=k.id, gross_weight_g=Decimal("1"), net_weight_g=Decimal("1"), fineness_ppt=Decimal("995"), fine_gold_g=Decimal("0.995"), recorded_by_id=u.id)
    db.add(ev)
    db.commit()
    db.refresh(head)
    db.refresh(lot)
    assert [t.code for t in head.team] == ["K-2"]
    assert k.head_karigar.code == "K-1"
    assert {x.code for x in org.karigars} == {"K-1", "K-2"}
    assert lot.events[0].to_karigar.code == "K-2"
    assert ev.job.head_karigar.code == "K-1"


def test_code_unique_per_org(db):
    org, _ = _org_user(db)
    db.add(Karigar(organisation_id=org.id, code="K-1", name="A", kind=KarigarKind.karigar))
    db.add(Karigar(organisation_id=org.id, code="K-1", name="B", kind=KarigarKind.karigar))
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_code_allowed_in_other_org(db):
    org1, _ = _org_user(db)
    org2, _ = _org_user(db)
    db.add_all([Karigar(organisation_id=org1.id, code="K-1", name="A", kind=KarigarKind.karigar), Karigar(organisation_id=org2.id, code="K-1", name="B", kind=KarigarKind.karigar)])
    db.flush()


def test_foreign_keys_enforced(db):
    db.add(Karigar(organisation_id=uuid.uuid4(), code="K-9", name="Orphan", kind=KarigarKind.karigar))
    with pytest.raises(IntegrityError):
        db.flush()


def test_lot_check_constraints(db):
    org, u = _org_user(db)
    db.add(MaterialLot(organisation_id=org.id, code="L-X", gross_weight_g=Decimal("5"), net_weight_g=Decimal("6"), stone_weight_g=Decimal("0"), fineness_ppt=Decimal("995"), fine_gold_g=Decimal("1"), created_by_id=u.id))
    with pytest.raises(IntegrityError):
        db.flush()
