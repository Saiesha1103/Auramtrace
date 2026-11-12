"""Lot receipt, issuance and acknowledgement workflows."""

from tests.conftest import MEAS, issue


def test_lot_records_gross_net_fineness_separately(client, admin):
    r = client.post("/api/v1/lots", headers=admin["h"], json={"source": "Finished return test", "grossWeightG": 31.5, "netWeightG": 31.284, "finenessPpt": 916, "measurement": MEAS})
    assert r.status_code == 201, r.text
    lot = r.json()
    assert lot["code"] == "L-0001"
    assert (lot["grossWeightG"], lot["netWeightG"], lot["stoneWeightG"], lot["finenessPpt"], lot["fineGoldG"]) == (31.5, 31.284, 0.216, 916.0, 28.656)
    assert lot["balance"]["vault"] == {"grossWeightG": 31.5, "netWeightG": 31.284, "fineGoldG": 28.656}
    ev = client.get(f"/api/v1/events?lotId={lot['id']}", headers=admin["h"]).json()["items"]
    assert len(ev) == 1 and ev[0]["eventType"] == "lot_received"
    assert ev[0]["from"]["type"] == "external" and ev[0]["to"]["type"] == "vault"
    assert ev[0]["measurement"] == {"scaleId": "SC-01", "operatorName": "Vault desk", "method": "manual"}


def test_lot_requires_provenance_and_precision(client, admin):
    r = client.post("/api/v1/lots", headers=admin["h"], json={"grossWeightG": 10, "netWeightG": 10, "finenessPpt": 995})
    assert r.status_code == 422 and any(d["field"] == "measurement" for d in r.json()["error"]["details"])
    r = client.post("/api/v1/lots", headers=admin["h"], json={"grossWeightG": 10.0001, "netWeightG": 10, "finenessPpt": 995, "measurement": MEAS})
    assert r.status_code == 422
    r = client.post("/api/v1/lots", headers=admin["h"], json={"grossWeightG": -1, "netWeightG": -1, "finenessPpt": 995, "measurement": MEAS})
    assert r.status_code == 422


def test_issue_and_acknowledge_flow(client, world):
    h = world["h"]
    r = issue(client, world, net=20)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["eventType"] == "issue" and ev["fineGoldG"] == 19.9 and ev["challanRef"] == "JWC-26-3301"
    assert ev["from"]["type"] == "vault" and ev["to"] == {"type": "karigar", "karigarId": world["head"]["id"], "karigarCode": "K-02", "karigarName": "Farida Shaikh"}
    assert ev["state"] == {"reversed": False, "reversalEventId": None, "acknowledged": False, "acknowledgementEventId": None}

    job = client.get(f"/api/v1/jobs/{world['job']['id']}", headers=h).json()
    assert job["status"] == "issued" and job["pendingAcknowledgements"] == 1
    assert job["issued"]["netWeightG"] == 20 and job["issued"]["fineGoldG"] == 19.9
    assert job["custody"][0]["karigarCode"] == "K-02"

    lot = client.get(f"/api/v1/lots/{world['lot']['id']}", headers=h).json()
    assert lot["balance"]["vault"]["netWeightG"] == 10.151 and lot["balance"]["withKarigars"]["netWeightG"] == 20

    r = client.post(f"/api/v1/events/{ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Farida Shaikh", "evidenceRef": "ACK-3301"})
    assert r.status_code == 201
    ack = r.json()
    assert ack["eventType"] == "issue_acknowledged" and ack["refEventId"] == ev["id"] and ack["grossWeightG"] is None
    issued = client.get(f"/api/v1/events/{ev['id']}", headers=h).json()
    assert issued["state"]["acknowledged"] is True and issued["state"]["acknowledgementEventId"] == ack["id"]

    prof = client.get(f"/api/v1/karigars/{world['head']['id']}", headers=h).json()
    assert prof["custody"]["fineGoldG"] == 19.9 and prof["custody"]["pendingAcknowledgements"] == 0
    assert prof["custody"]["byJob"][0]["jobCode"] == "J-1182"


def test_cannot_acknowledge_twice_or_non_issue(client, world):
    h = world["h"]
    ev = issue(client, world, net=5).json()
    assert client.post(f"/api/v1/events/{ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Farida Shaikh"}).status_code == 201
    r = client.post(f"/api/v1/events/{ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Farida Shaikh"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_acknowledged"
    receipt = client.get(f"/api/v1/events?lotId={world['lot']['id']}&eventType=lot_received", headers=h).json()["items"][0]
    r = client.post(f"/api/v1/events/{receipt['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Someone"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_acknowledgeable"


def test_over_issue_rejected_and_fine_gold_has_no_drift(client, world):
    h = world["h"]
    assert issue(client, world, net=15.075).status_code == 201
    assert issue(client, world, net=15.076, karigar_id=world["karigar"]["id"]).status_code == 201
    r = issue(client, world, net=0.001)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "insufficient_balance" and err["details"]["availableNetWeightG"] == 0
    # 15.075 → 15.000 and 15.076 → 15.001 individually; the lot total stays exactly 30.000 g fine
    lot = client.get(f"/api/v1/lots/{world['lot']['id']}", headers=h).json()
    assert lot["balance"]["withKarigars"] == {"grossWeightG": 30.151, "netWeightG": 30.151, "fineGoldG": 30.0}
    assert lot["balance"]["vault"]["netWeightG"] == 0


def test_issue_rules(client, world):
    h = world["h"]
    r = issue(client, world, net=5, gross=4)
    assert r.status_code == 422  # net > gross
    client.patch(f"/api/v1/karigars/{world['karigar']['id']}", headers=h, json={"status": "inactive"})
    r = issue(client, world, net=1, karigar_id=world["karigar"]["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "karigar_inactive"
    j2 = client.post("/api/v1/jobs", headers=h, json={"title": "To cancel", "karat": "22K", "pieces": 1, "dueDate": "2026-12-01"}).json()
    client.patch(f"/api/v1/jobs/{j2['id']}", headers=h, json={"status": "cancelled"})
    r = client.post(f"/api/v1/lots/{world['lot']['id']}/issue", headers=h, json={"jobId": j2["id"], "karigarId": world["head"]["id"], "grossWeightG": 1, "netWeightG": 1, "measurement": MEAS})
    assert r.status_code == 422 and r.json()["error"]["code"] == "job_cancelled"


def test_cannot_cancel_job_with_custody(client, world):
    issue(client, world, net=1)
    r = client.patch(f"/api/v1/jobs/{world['job']['id']}", headers=world["h"], json={"status": "cancelled"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "job_has_custody"


def test_event_history_filters(client, world):
    h = world["h"]
    issue(client, world, net=10)
    issue(client, world, net=5, karigar_id=world["karigar"]["id"])
    all_ev = client.get("/api/v1/events", headers=h).json()
    assert all_ev["total"] == 3
    assert [e["eventType"] for e in all_ev["items"]] == ["lot_received", "issue", "issue"]
    assert client.get(f"/api/v1/events?karigarId={world['karigar']['id']}", headers=h).json()["total"] == 1
    assert client.get(f"/api/v1/events?jobId={world['job']['id']}&eventType=issue", headers=h).json()["total"] == 2
    assert client.get("/api/v1/events?limit=1&offset=1", headers=h).json()["items"][0]["eventType"] == "issue"
    assert all(e["recordedAt"].endswith("Z") for e in all_ev["items"])


def test_writes_are_audited(client, world):
    ev = issue(client, world, net=1).json()
    acts = [a["action"] for a in client.get("/api/v1/audit", headers=world["h"]).json()["items"]]
    assert acts[0] == "material.issued"
    assert {"organisation.registered", "karigar.created", "job.created", "lot.created"} <= set(acts)
    assert ev["recordedBy"]["fullName"] == "Test Admin"
