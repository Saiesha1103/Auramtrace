"""Karigar directory/profile/hierarchy and job APIs."""


def test_karigar_codes_generated_and_hierarchy(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"name": "Mahesh Soni", "kind": "head_karigar"}).json()
    assert head["code"] == "K-0001" and head["status"] == "active" and head["skills"] == []
    k = client.post("/api/v1/karigars", headers=h, json={"name": "Ravi Kumar", "kind": "karigar", "headKarigarId": head["id"], "skills": ["Casting"]}).json()
    sub = client.post("/api/v1/karigars", headers=h, json={"name": "Shree Casting Works", "kind": "subcontractor", "headKarigarId": head["id"]}).json()
    indie = client.post("/api/v1/karigars", headers=h, json={"name": "Independent Artisan", "kind": "karigar"}).json()
    tree = client.get("/api/v1/karigars/hierarchy", headers=h).json()
    roots = {n["code"]: n for n in tree}
    assert set(roots) == {head["code"], indie["code"]}
    assert {c["code"] for c in roots[head["code"]]["children"]} == {k["code"], sub["code"]}
    assert roots[head["code"]]["fineGoldHeldG"] == 0


def test_hierarchy_rules(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"name": "Head One", "kind": "head_karigar"}).json()
    k = client.post("/api/v1/karigars", headers=h, json={"name": "Worker One", "kind": "karigar"}).json()
    # a karigar cannot be anyone's head
    r = client.post("/api/v1/karigars", headers=h, json={"name": "Worker Two", "kind": "karigar", "headKarigarId": k["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_hierarchy"
    # head karigars report to the manufacturer, not another head
    r = client.post("/api/v1/karigars", headers=h, json={"name": "Head Two", "kind": "head_karigar", "headKarigarId": head["id"]})
    assert r.status_code == 422
    # duplicate code
    client.post("/api/v1/karigars", headers=h, json={"code": "K-77", "name": "A A", "kind": "karigar"})
    r = client.post("/api/v1/karigars", headers=h, json={"code": "K-77", "name": "B B", "kind": "karigar"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_code"


def test_karigar_list_filters_and_update(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"name": "Farida Shaikh", "kind": "head_karigar", "unit": "Kalbadevi"}).json()
    k = client.post("/api/v1/karigars", headers=h, json={"name": "Anil Verma", "kind": "karigar", "headKarigarId": head["id"]}).json()
    assert client.get("/api/v1/karigars?kind=head_karigar", headers=h).json()["total"] == 1
    assert client.get("/api/v1/karigars?q=kalba", headers=h).json()["items"][0]["id"] == head["id"]
    assert client.get(f"/api/v1/karigars?headKarigarId={head['id']}", headers=h).json()["total"] == 1
    # head with an active team can't be deactivated
    r = client.patch(f"/api/v1/karigars/{head['id']}", headers=h, json={"status": "inactive"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "has_active_team"
    r = client.patch(f"/api/v1/karigars/{k['id']}", headers=h, json={"status": "inactive", "contact": "+91 90000 00000"})
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    audit = client.get(f"/api/v1/audit?entityType=karigar&entityId={k['id']}", headers=h).json()["items"]
    assert audit[0]["action"] == "karigar.updated" and audit[0]["details"]["status"] == {"from": "active", "to": "inactive"}


def test_karigar_profile(client, world):
    p = client.get(f"/api/v1/karigars/{world['head']['id']}", headers=world["h"]).json()
    assert [t["code"] for t in p["team"]] == ["K-07"]
    assert p["headKarigar"] is None
    assert p["custody"] == {"fineGoldG": 0, "netWeightG": 0, "grossWeightG": 0, "pendingAcknowledgements": 0, "byJob": []}


def test_job_create_defaults_and_detail(client, admin):
    h = admin["h"]
    j = client.post("/api/v1/jobs", headers=h, json={"title": "Coin pendants", "karat": "24K", "pieces": 30, "targetGrossPerPieceG": 1, "dueDate": "2026-11-18"}).json()
    assert j["code"] == "J-0001" and j["status"] == "draft"
    assert j["targetFinenessPpt"] == 995.0 and j["lossAllowancePct"] == "1.0" or j["lossAllowancePct"] == 1.0
    d = client.get(f"/api/v1/jobs/{j['id']}", headers=h).json()
    assert d["issued"] == {"grossWeightG": 0, "netWeightG": 0, "fineGoldG": 0} and d["events"] == [] and d["custody"] == []


def test_job_validation(client, admin):
    h = admin["h"]
    r = client.post("/api/v1/jobs", headers=h, json={"title": "Bad", "karat": "21K", "pieces": 0, "lossAllowancePct": 9, "dueDate": "not-a-date"})
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"karat", "pieces", "lossAllowancePct", "dueDate"} <= fields


def test_job_list_filters_and_cancel(client, world):
    h = world["h"]
    other = client.post("/api/v1/jobs", headers=h, json={"title": "Nose pins", "karat": "18K", "pieces": 40, "dueDate": "2026-12-05"}).json()
    assert client.get("/api/v1/jobs?q=temple", headers=h).json()["total"] == 1
    assert client.get("/api/v1/jobs?status=draft", headers=h).json()["total"] == 2
    r = client.patch(f"/api/v1/jobs/{other['id']}", headers=h, json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.patch(f"/api/v1/jobs/{other['id']}", headers=h, json={"title": "Edited"}).status_code == 422
