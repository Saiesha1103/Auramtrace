"""Tests for material return workflows, scrap, dust, WIP, and assay updates."""

import pytest


MEAS = {"scaleId": "SC-VAULT-01", "operatorName": "Vault Officer", "method": "manual"}


@pytest.fixture()
def return_world(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-RET-HEAD", "name": "Deepak Master", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-PENDANT",
        "title": "Temple Pendant",
        "karat": "22K",
        "pieces": 5,
        "lossAllowancePct": 1.2,
        "headKarigarId": head["id"],
        "dueDate": "2026-12-20",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-22K-RET",
        "source": "Bar 916",
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()
    # Issue 25.000 g to head
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 25.000,
        "netWeightG": 25.000,
        "measurement": MEAS,
    })
    return {"h": h, "head": head, "job": job, "lot": lot}


def test_finished_goods_return_and_custody_transfer(client, return_world):
    w = return_world
    h = w["h"]

    # Karigar returns 20.000 g finished jewellery (with 2.500 g stones, 17.500 g net gold)
    r = client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 20.000,
        "netMetalWeightG": 17.500,
        "stoneWeightG": 2.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 5,
        "isPartial": True,
        "measurement": MEAS,
        "challanRef": "RET-FG-01",
    })
    assert r.status_code == 201
    ret = r.json()
    assert ret["returnCategory"] == "finished_jewellery"
    assert ret["grossWeightG"] == 20.0
    assert ret["netMetalWeightG"] == 17.5
    assert ret["stoneWeightG"] == 2.5
    # Fine gold: 17.500 * 916.0 / 1000 = 16.030
    assert ret["fineGoldG"] == 16.03

    # Karigar net custody decreased by 17.500 g: 25.000 - 17.500 = 7.500 g
    head_p = client.get(f"/api/v1/karigars/{w['head']['id']}", headers=h).json()
    assert head_p["custody"]["netWeightG"] == 7.5

    # Vault balance increased by 17.500 g
    lot_view = client.get(f"/api/v1/lots/{w['lot']['id']}", headers=h).json()
    # Vault had 5.000 g unissued + 17.500 g returned = 22.500 g
    assert lot_view["balance"]["vault"]["netWeightG"] == 22.5


def test_scrap_and_dust_returns_with_retained_scrap(client, return_world):
    w = return_world
    h = w["h"]

    # Karigar returns 6.000 g scrap, with 0.500 g retained scrap held at workshop
    r = client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 6.000,
        "netMetalWeightG": 6.000,
        "stoneWeightG": 0.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "retainedScrapG": 0.500,
        "measurement": MEAS,
    })
    assert r.status_code == 201
    ret = r.json()
    assert ret["retainedScrapG"] == 0.5
    assert ret["returnCategory"] == "scrap"

    # Because isPartial was False, job status moves to returned
    job = client.get(f"/api/v1/jobs/{w['job']['id']}", headers=h).json()
    assert job["status"] == "returned"


def test_assay_result_update(client, return_world):
    w = return_world
    h = w["h"]

    ret = client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 10.000,
        "netMetalWeightG": 10.000,
        "declaredFinenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Verified fire assay reveals 910.0 ppt (shortfall)
    r = client.post(f"/api/v1/returns/{ret['id']}/assay", headers=h, json={
        "assayedFinenessPpt": 910.0,
        "assayEvidenceRef": "CERT-ASSAY-7721",
        "notes": "Verified by National Assay Laboratory",
    })
    assert r.status_code == 200
    updated = r.json()
    assert updated["assayedFinenessPpt"] == 910.0
    # Fine gold recalculated: 10.000 * 910.0 / 1000 = 9.100
    assert updated["fineGoldG"] == 9.1
