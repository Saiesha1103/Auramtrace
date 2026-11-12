"""Custody history cannot be silently overwritten: ORM guard, DB triggers, API surface, reversals."""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.errors import AppendOnlyViolation
from app.models import AuditEvent, MaterialEvent
from tests.conftest import issue


def _first_event(db):
    return db.scalars(select(MaterialEvent)).first()


def test_orm_update_and_delete_blocked(world, SessionLocal):
    s = SessionLocal()
    ev = _first_event(s)
    ev.note = "tampered"
    with pytest.raises(AppendOnlyViolation):
        s.flush()
    s.rollback()
    ev = _first_event(s)
    s.delete(ev)
    with pytest.raises(AppendOnlyViolation):
        s.flush()
    s.rollback()
    s.close()


@pytest.mark.parametrize("sql", ["UPDATE material_events SET note = 'tampered'", "DELETE FROM material_events", "UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"])
def test_database_triggers_block_raw_sql(world, engine, sql):
    with engine.connect() as c:
        with pytest.raises((IntegrityError, DBAPIError)) as exc:
            c.execute(text(sql))
        assert "append-only" in str(exc.value)
        c.rollback()


def test_bulk_orm_update_blocked_by_trigger(world, SessionLocal):
    s = SessionLocal()
    with pytest.raises((IntegrityError, DBAPIError)):
        s.execute(update(MaterialEvent).values(note="bulk tamper"))
        s.flush()
    s.rollback()
    s.close()


def test_no_mutation_endpoints(client, world):
    ev = client.get("/api/v1/events", headers=world["h"]).json()["items"][0]
    for method in ("put", "patch", "delete"):
        r = getattr(client, method)(f"/api/v1/events/{ev['id']}", headers=world["h"])
        assert r.status_code == 405, method
        assert r.json()["error"]["code"] == "method_not_allowed"


def test_reversal_appends_and_preserves_original(client, world, SessionLocal):
    h = world["h"]
    ev = issue(client, world, net=10).json()
    r = client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "Issued against wrong karigar"})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["eventType"] == "reversal" and rev["refEventId"] == ev["id"] and rev["note"] == "Issued against wrong karigar"
    assert rev["from"]["karigarId"] == world["head"]["id"] and rev["to"]["type"] == "vault"
    # the original row is byte-for-byte unchanged and now reports its reversal
    s = SessionLocal()
    orig = s.get(MaterialEvent, uuid.UUID(ev["id"]))
    assert orig.event_type == "issue" and str(orig.net_weight_g) == "10.000" and orig.note is None
    s.close()
    after = client.get(f"/api/v1/events/{ev['id']}", headers=h).json()
    assert after["state"]["reversed"] is True and after["state"]["reversalEventId"] == rev["id"]
    # balances are restored by summing both rows
    lot = client.get(f"/api/v1/lots/{world['lot']['id']}", headers=h).json()
    assert lot["balance"]["vault"]["netWeightG"] == 30.151
    job = client.get(f"/api/v1/jobs/{world['job']['id']}", headers=h).json()
    assert job["status"] == "draft" and job["issued"]["netWeightG"] == 0
    assert [e["eventType"] for e in job["events"]] == ["issue", "reversal"]


def test_reversal_rules(client, world):
    h = world["h"]
    ev = issue(client, world, net=10).json()
    rev = client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "first correction"}).json()
    r = client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "second correction"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_reversed"
    r = client.post(f"/api/v1/events/{rev['id']}/reverse", headers=h, json={"reason": "undo the undo"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_reversible"
    r = client.post(f"/api/v1/events/{ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Farida Shaikh"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "event_reversed"
    r = client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "no"})
    assert r.status_code == 422  # reason too short


def test_acknowledged_issue_needs_ack_reversal_first(client, world):
    h = world["h"]
    ev = issue(client, world, net=10).json()
    ack = client.post(f"/api/v1/events/{ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Farida Shaikh"}).json()
    r = client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "wrong weight entered"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "acknowledged_issue"
    assert client.post(f"/api/v1/events/{ack['id']}/reverse", headers=h, json={"reason": "signature was for another lot"}).status_code == 201
    assert client.get(f"/api/v1/events/{ev['id']}", headers=h).json()["state"]["acknowledged"] is False
    assert client.post(f"/api/v1/events/{ev['id']}/reverse", headers=h, json={"reason": "wrong weight entered"}).status_code == 201


def test_receipt_reversal_blocked_while_metal_is_out(client, world):
    h = world["h"]
    issue(client, world, net=1)
    receipt = client.get(f"/api/v1/events?lotId={world['lot']['id']}&eventType=lot_received", headers=h).json()["items"][0]
    r = client.post(f"/api/v1/events/{receipt['id']}/reverse", headers=h, json={"reason": "duplicate receipt"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "lot_in_use"


def test_audit_rows_are_append_only_too(world, SessionLocal):
    s = SessionLocal()
    a = s.scalars(select(AuditEvent)).first()
    a.action = "rewritten"
    with pytest.raises(AppendOnlyViolation):
        s.flush()
    s.rollback()
    s.close()
