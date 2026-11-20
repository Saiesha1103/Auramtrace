"""Agentic AI, karigar portal, two-party settlement, payments, occasion dates and track record."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.conftest import PASSWORD, auth

MEAS = {"scaleId": "SC-AG-01", "operatorName": "Vault desk", "method": "manual"}


def today():
    return datetime.now(UTC).date()


# ------------------------------------------------------------------ fixtures


@pytest.fixture()
def shop(client, admin, make_user):
    """Two karigars, each with a portal login; a job for Anil that is returned and reconciled."""
    h = admin["h"]
    anil = client.post("/api/v1/karigars", headers=h, json={"code": "K-AN", "name": "Anil Verma", "kind": "head_karigar"}).json()
    ravi = client.post("/api/v1/karigars", headers=h, json={"code": "K-RV", "name": "Ravi Soni", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-WED-01", "title": "Bridal choker", "karat": "22K", "pieces": 1, "lossAllowancePct": 1.5,
        "headKarigarId": anil["id"], "dueDate": str(today() + timedelta(days=20)),
        "occasionDate": str(today() + timedelta(days=25)), "occasionLabel": "Wedding - Sharma family",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={"code": "L-AG-1", "source": "916 bar", "grossWeightG": 50, "netWeightG": 50, "finenessPpt": 916, "measurement": MEAS}).json()
    issue = client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={"jobId": job["id"], "karigarId": anil["id"], "grossWeightG": 40, "netWeightG": 40, "measurement": MEAS}).json()
    ret = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"], "karigarId": anil["id"], "lotId": lot["id"], "returnCategory": "finished_jewellery",
        "grossWeightG": 39.5, "netMetalWeightG": 39.5, "declaredFinenessPpt": 916, "pieces": 1, "measurement": MEAS,
    })
    assert ret.status_code == 201, ret.text
    assert client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h).status_code == 201

    def login_for(k, email):
        r = client.post("/api/v1/users", headers=h, json={"email": email, "fullName": k["name"], "role": "karigar", "password": PASSWORD, "karigarId": k["id"]})
        assert r.status_code == 201, r.text
        tok = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["accessToken"]
        return auth(tok)

    return {
        "h": h, "anil": anil, "ravi": ravi, "job": job, "lot": lot, "issue": issue,
        "anil_h": login_for(anil, "anil@aurumtrace-test.example.com"),
        "ravi_h": login_for(ravi, "ravi@aurumtrace-test.example.com"),
        "mgr": make_user("manager", "approver@aurumtrace-test.example.com"),
    }


def approved_sheet(client, s):
    ws = client.post("/api/v1/settlements/worksheets", headers=s["h"], json={"jobId": s["job"]["id"]}).json()
    assert client.post(f"/api/v1/settlements/worksheets/{ws['id']}/submit", headers=s["h"]).status_code == 200
    r = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/approve", headers=s["mgr"]["h"], json={})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    return ws


# ------------------------------------------------------------------ karigar logins & isolation


def test_karigar_login_creation_rules(client, admin, shop):
    h = admin["h"]
    base = {"fullName": "Some One", "password": PASSWORD}
    r = client.post("/api/v1/users", headers=h, json={**base, "email": "a@aurumtrace-test.example.com", "role": "karigar"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "karigar_required"
    r = client.post("/api/v1/users", headers=h, json={**base, "email": "b@aurumtrace-test.example.com", "role": "manager", "karigarId": shop["ravi"]["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "karigar_link_not_allowed"
    r = client.post("/api/v1/users", headers=h, json={**base, "email": "c@aurumtrace-test.example.com", "role": "karigar", "karigarId": shop["anil"]["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "karigar_login_exists"


def test_karigar_login_is_denied_every_staff_endpoint(client, shop):
    kh = shop["anil_h"]
    assert client.get("/api/v1/auth/me", headers=kh).json()["role"] == "karigar"
    for path in ("/api/v1/jobs", "/api/v1/karigars", "/api/v1/lots", "/api/v1/settlements/worksheets", "/api/v1/events",
                 f"/api/v1/karigars/{shop['ravi']['id']}", "/api/v1/reconciliations", "/api/v1/exceptions", "/api/v1/agents/runs",
                 f"/api/v1/investigations/tools/get_job_summary?jobId={shop['job']['id']}"):
        r = client.get(path, headers=kh)
        assert r.status_code == 403, (path, r.status_code)
    assert client.post("/api/v1/agents/watch", headers=kh, json={}).status_code == 403
    # and staff cannot use the portal
    assert client.get("/api/v1/portal/me", headers=shop["h"]).status_code == 403


def test_portal_shows_only_my_own_account(client, shop):
    me = client.get("/api/v1/portal/me", headers=shop["anil_h"])
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["karigar"]["code"] == "K-AN"
    assert body["trackRecord"]["jobsDelivered"] == 1

    assert [j["code"] for j in client.get("/api/v1/portal/jobs", headers=shop["anil_h"]).json()] == ["J-WED-01"]
    assert client.get("/api/v1/portal/jobs", headers=shop["ravi_h"]).json() == []
    assert len(client.get("/api/v1/portal/ledger", headers=shop["anil_h"]).json()) >= 2
    assert client.get("/api/v1/portal/ledger", headers=shop["ravi_h"]).json() == []


def test_karigar_acknowledges_own_receipt_only(client, shop):
    ev = shop["issue"]["id"]
    assert client.post(f"/api/v1/portal/events/{ev}/acknowledge", headers=shop["ravi_h"], json={}).status_code == 404
    r = client.post(f"/api/v1/portal/events/{ev}/acknowledge", headers=shop["anil_h"], json={"evidenceRef": "My scale: 40.000 g"})
    assert r.status_code == 201, r.text
    assert r.json()["eventType"] == "issue_acknowledged"
    assert client.post(f"/api/v1/portal/events/{ev}/acknowledge", headers=shop["anil_h"], json={}).status_code == 409


# ------------------------------------------------------------------ two-party settlement & payment


def test_two_party_settlement_dispute_then_accept_then_pay(client, shop):
    h = shop["h"]
    ws = approved_sheet(client, shop)

    # cannot pay before the karigar accepts
    r = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/mark-paid", headers=h, json={"paymentRef": "UPI-1"})
    assert r.status_code == 422

    # another karigar cannot see or answer it
    assert client.post(f"/api/v1/portal/settlements/{ws['id']}/accept", headers=shop["ravi_h"], json={}).status_code == 404
    assert client.get("/api/v1/portal/settlements", headers=shop["ravi_h"]).json() == []

    # Anil disputes with a reason; jeweller rejects and issues a corrected sheet
    r = client.post(f"/api/v1/portal/settlements/{ws['id']}/dispute", headers=shop["anil_h"], json={"reason": "My scale showed 39.800 g returned, challan attached"})
    assert r.status_code == 200 and r.json()["status"] == "disputed"
    assert r.json()["disputeReason"].startswith("My scale")
    assert client.post(f"/api/v1/portal/settlements/{ws['id']}/accept", headers=shop["anil_h"], json={}).status_code == 422
    assert client.post(f"/api/v1/settlements/worksheets/{ws['id']}/reject", headers=h, json={"reason": "Re-weighed together"}).status_code == 200

    ws2 = approved_sheet(client, shop)
    assert client.get(f"/api/v1/jobs/{shop['job']['id']}", headers=h).json()["status"] != "settled"
    r = client.post(f"/api/v1/portal/settlements/{ws2['id']}/accept", headers=shop["anil_h"], json={"note": "Agreed"})
    assert r.status_code == 200 and r.json()["status"] == "karigar_accepted"
    assert client.get(f"/api/v1/jobs/{shop['job']['id']}", headers=h).json()["status"] == "settled"

    # karigar cannot mark themselves paid; manager can
    assert client.post(f"/api/v1/settlements/worksheets/{ws2['id']}/mark-paid", headers=shop["anil_h"], json={"paymentRef": "x1"}).status_code == 403
    r = client.post(f"/api/v1/settlements/worksheets/{ws2['id']}/mark-paid", headers=h, json={"paymentRef": "UPI 4417 2291"})
    assert r.status_code == 200 and r.json()["status"] == "paid" and r.json()["paidAt"]

    tr = client.get(f"/api/v1/karigars/{shop['anil']['id']}/track-record", headers=h).json()
    assert tr["settlementsPaid"] == 1 and tr["settlementsDisputed"] == 1 and tr["averageDaysToPayment"] == 0
    assert tr["onTimeDeliveries"] == 1

    actions = [a["action"] for a in client.get("/api/v1/audit", headers=h, params={"entityType": "settlement_worksheet"}).json()["items"]]
    assert {"settlement.karigar_disputed", "settlement.karigar_accepted", "settlement.paid"} <= set(actions)


# ------------------------------------------------------------------ agent runtime


class ScriptedPlanner:
    """A stand-in LLM: returns pre-scripted turns and records what it was shown."""

    name = "scripted_test_llm"

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen_contents = []

    def next_turn(self, system, contents, tools):
        self.seen_contents.append(json.loads(json.dumps(contents)))
        t = self.turns.pop(0)
        return t(contents) if callable(t) else t


def call(name, **args):
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def text(obj):
    return {"role": "model", "parts": [{"text": "```json\n" + json.dumps(obj) + "\n```"}]}


def _purity_case(client, shop):
    # assay a heavy purity shortfall onto a new return so detection raises a case
    h = shop["h"]
    lot = client.post("/api/v1/lots", headers=h, json={"code": "L-AG-2", "source": "916", "grossWeightG": 20, "netWeightG": 20, "finenessPpt": 916, "measurement": MEAS}).json()
    job = client.post("/api/v1/jobs", headers=h, json={"code": "J-PUR", "title": "Rings", "karat": "22K", "pieces": 2, "headKarigarId": shop["ravi"]["id"], "dueDate": "2026-01-01"}).json()
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={"jobId": job["id"], "karigarId": shop["ravi"]["id"], "grossWeightG": 20, "netWeightG": 20, "measurement": MEAS})
    ret = client.post("/api/v1/returns", headers=h, json={"jobId": job["id"], "karigarId": shop["ravi"]["id"], "lotId": lot["id"], "returnCategory": "finished_jewellery",
                                                          "grossWeightG": 19, "netMetalWeightG": 19, "declaredFinenessPpt": 916, "assayedFinenessPpt": 880, "measurement": MEAS}).json()
    client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h)
    cases = client.post(f"/api/v1/exceptions/detect?jobId={job['id']}", headers=h).json()
    case = next(c for c in cases if c["exceptionType"] == "purity_mismatch")
    return case, job, ret


def test_rule_planner_investigation_runs_a_real_tool_loop(client, shop):
    case, job, ret = _purity_case(client, shop)
    inv = client.post("/api/v1/investigations/run", headers=shop["h"], json={"exceptionId": case["id"]})
    assert inv.status_code == 201, inv.text
    resp = inv.json()["response"]
    assert inv.json()["provider"] == "rule_planner_v1"
    trace = resp["agentTrace"]
    assert trace[0]["tool"] == "get_exception_details"
    assert {"get_job_summary", "get_reconciliation", "get_material_returns", "trace_karigar_custody"} <= set(resp["agent"]["toolsUsed"])
    assert resp["agent"]["readOnly"] is True and trace[-1]["type"] == "final"
    assert any(e["recordId"] == ret["id"] for e in resp["evidence"])


def test_llm_agent_loop_validates_tools_scopes_org_and_grounds_answer(client, shop, monkeypatch):
    case, job, ret = _purity_case(client, shop)
    # a second organisation whose job id the "model" will try to read
    other = client.post("/api/v1/auth/register", json={"organisationName": "Other Shop", "fullName": "Other Admin", "email": "other@aurumtrace-test.example.com", "password": PASSWORD}).json()
    oh = auth(other["accessToken"])
    ok = client.post("/api/v1/karigars", headers=oh, json={"code": "K-X", "name": "Xavier", "kind": "head_karigar"}).json()
    foreign_job = client.post("/api/v1/jobs", headers=oh, json={"code": "J-X", "title": "Secret", "karat": "22K", "pieces": 1, "headKarigarId": ok["id"], "dueDate": "2026-12-01"}).json()

    planner = ScriptedPlanner([
        call("get_exception_details", exception_id=case["id"]),
        call("get_job_summary", job_id=foreign_job["id"]),        # other organisation → not found
        call("get_job_summary", job_id="not-a-uuid"),              # invalid argument
        call("approve_settlement", worksheet_id=case["id"]),       # not a tool: agents cannot write
        call("get_material_returns", job_id=job["id"]),
        text({
            "summary": "Ravi's return assayed 880 ppt against 916 declared.",
            "verifiedFacts": [
                {"fact": "Assay 880 ppt", "recordId": ret["id"], "field": "assayedFinenessPpt", "observedValue": "880"},
                {"fact": "Invented record", "recordId": "00000000-0000-0000-0000-000000000001"},
            ],
            "evidence": [{"evidenceType": "MaterialReturn", "recordId": ret["id"], "field": "assayedFinenessPpt", "observedValue": "880", "explanation": "shortfall"}],
            "suspectedCauses": [{"cause": "Fineness shortfall", "probability": 0.9, "rationale": "36 ppt below declared"}],
            "recommendedActions": [], "missingEvidence": [], "calculationBreakdown": {}, "confidence": 0.88, "limitations": [],
            "exceptionId": "spoofed", "jobId": "spoofed",
        }),
    ])
    from app.services import ai_investigation

    monkeypatch.setattr(ai_investigation, "_make_llm_planner", lambda: planner)
    r = client.post("/api/v1/investigations/run", headers=shop["h"], json={"exceptionId": case["id"]})
    assert r.status_code == 201, r.text
    out = r.json()
    resp = out["response"]
    assert out["provider"] == "scripted_test_llm"
    calls = [t for t in resp["agentTrace"] if t["type"] == "tool_call"]
    assert [c["ok"] for c in calls] == [True, False, False, False, True]
    assert "not found" in calls[1]["error"].lower()
    assert "uuid" in calls[2]["error"].lower()
    assert "unknown tool" in calls[3]["error"]
    # the foreign organisation's data never reached the model
    assert "Secret" not in json.dumps(planner.seen_contents)
    # ungrounded fact removed; identifiers are ours
    assert [f["recordId"] for f in resp["verifiedFacts"]] == [ret["id"]]
    assert any("removed" in l for l in resp["limitations"])
    assert resp["exceptionId"] == case["id"] and resp["jobId"] == job["id"]


def test_llm_agent_failure_falls_back_to_rule_planner(client, shop, monkeypatch):
    case, _, _ = _purity_case(client, shop)

    def boom(contents):
        raise httpx.ConnectError("offline")

    from app.services import ai_investigation

    monkeypatch.setattr(ai_investigation, "_make_llm_planner", lambda: ScriptedPlanner([call("get_exception_details", exception_id=case["id"]), boom]))
    out = client.post("/api/v1/investigations/run", headers=shop["h"], json={"exceptionId": case["id"]}).json()
    assert out["provider"] == "rule_planner_v1 (gemini_fallback)"
    assert any(t["type"] == "llm_failed" for t in out["response"]["agentTrace"])
    assert out["response"]["verifiedFacts"]


def test_agent_stops_at_max_steps(db):
    import uuid as _uuid

    from app.services.agent_runtime import Tool, run_agent

    t = Tool("noop", "does nothing", (), lambda db, org: {"ok": True})
    res = run_agent(db, _uuid.uuid4(), goal="loop", system="", tools=[t], planner=ScriptedPlanner([call("noop")] * 20), max_steps=3)
    assert res.stopped_reason == "max_steps" and res.final is None and len(res.trace) == 3


def test_gemini_planner_wire_format():
    """Function declarations go out, the key goes in a header (not the URL), and the model turn comes back as-is."""
    from app.services.agent_runtime import GeminiPlanner, Tool, ToolParam

    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "get_job_summary", "args": {"job_id": "x"}}, "thoughtSignature": "sig"}]}}]})

    p = GeminiPlanner("test-key-not-real", transport=httpx.MockTransport(handler))
    tool = Tool("get_job_summary", "job", (ToolParam("job_id", "uuid", "job id"),), lambda db, org, job_id: {})
    turn = p.next_turn("sys", [{"role": "user", "parts": [{"text": "go"}]}], [tool])
    assert "key=" not in seen["url"] and seen["key"] == "test-key-not-real"
    decl = seen["body"]["tools"][0]["functionDeclarations"][0]
    assert decl["name"] == "get_job_summary" and decl["parameters"]["required"] == ["job_id"]
    assert turn["parts"][0]["thoughtSignature"] == "sig"


# ------------------------------------------------------------------ watcher agent


def test_watcher_flags_wedding_deadline_and_unpaid_karigar(client, shop):
    h = shop["h"]
    # Ravi holds gold for a wedding two days away
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-URGENT", "title": "Mangalsutra", "karat": "22K", "pieces": 1, "headKarigarId": shop["ravi"]["id"],
        "dueDate": str(today() + timedelta(days=1)), "occasionDate": str(today() + timedelta(days=2)), "occasionLabel": "Wedding - Iyer family",
    }).json()
    client.post(f"/api/v1/lots/{shop['lot']['id']}/issue", headers=h, json={"jobId": job["id"], "karigarId": shop["ravi"]["id"], "grossWeightG": 8, "netWeightG": 8, "measurement": MEAS})
    ws = approved_sheet(client, shop)
    client.post(f"/api/v1/portal/settlements/{ws['id']}/accept", headers=shop["anil_h"], json={})

    r = client.post("/api/v1/agents/watch", headers=h, json={"horizonDays": 7})
    assert r.status_code == 201, r.text
    run = r.json()
    out = run["output"]
    assert run["provider"] == "rule_planner_v1" and out["agent"]["sendsMessages"] is False
    crit = [a for a in out["alerts"] if a["severity"] == "critical"]
    assert crit and crit[0]["recordId"] == job["id"]
    assert any(a["kind"] == "payment" and a["recordId"] == ws["id"] for a in out["alerts"])
    ravi_draft = next(d for d in out["draftMessages"] if d["karigarId"] == shop["ravi"]["id"])
    assert "J-URGENT" in ravi_draft["text"] and "Wedding - Iyer family" in ravi_draft["text"]
    assert any(t.get("tool") == "get_karigar_track_record" for t in run["trace"])
    # the far-off wedding job is fully delivered, so not flagged
    assert all(a["recordId"] != shop["job"]["id"] for a in out["alerts"])

    listed = client.get("/api/v1/agents/runs", headers=h).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == run["id"]


def test_job_occasion_date_round_trip(client, shop):
    j = client.get(f"/api/v1/jobs/{shop['job']['id']}", headers=shop["h"]).json()
    assert j["occasionLabel"] == "Wedding - Sharma family"
    r = client.patch(f"/api/v1/jobs/{shop['job']['id']}", headers=shop["h"], json={"occasionDate": None})
    assert r.status_code == 200 and r.json()["occasionDate"] is None
