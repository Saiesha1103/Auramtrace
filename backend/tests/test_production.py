"""Tests for production tracking, manufacturing stages, and measurements."""

import pytest


MEAS = {"scaleId": "SC-BENCH-01", "operatorName": "Master Polisher", "method": "manual"}


@pytest.fixture()
def prod_world(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-PROD-HEAD", "name": "Vasant Master", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-BRACELET",
        "title": "Diamond-set Gold Bracelet",
        "karat": "18K",
        "pieces": 2,
        "lossAllowancePct": 1.8,
        "headKarigarId": head["id"],
        "dueDate": "2026-12-15",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-18K-BAR",
        "source": "18K Alloyed Bar",
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "finenessPpt": 750.0,
        "measurement": MEAS,
    }).json()
    # Issue to head
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 25.000,
        "netWeightG": 25.000,
        "measurement": MEAS,
    })
    return {"h": h, "head": head, "job": job, "lot": lot}


def test_production_entry_lifecycle(client, prod_world):
    w = prod_world
    h = w["h"]

    # 1. Create Casting production stage
    r = client.post("/api/v1/production", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "stage": "Casting",
        "note": "Centrifugal vacuum casting",
    })
    assert r.status_code == 201
    entry = r.json()
    assert entry["stage"] == "Casting"
    assert entry["status"] == "in_progress"
    assert entry["completedAt"] is None

    # Job status updated to in_production
    job = client.get(f"/api/v1/jobs/{w['job']['id']}", headers=h).json()
    assert job["status"] == "in_production"

    # 2. Complete production entry
    comp_r = client.post(f"/api/v1/production/{entry['id']}/complete", headers=h)
    assert comp_r.status_code == 200
    completed = comp_r.json()
    assert completed["status"] == "completed"
    assert completed["completedAt"] is not None


def test_production_measurement_and_stone_separation(client, prod_world):
    w = prod_world
    h = w["h"]

    # Record stone setting measurement
    # Input: 20.000 g net gold
    # Output: 23.500 g gross (including 3.800 g stones, 19.700 g net gold, 0.300 g filing loss)
    r = client.post("/api/v1/production/measurements", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "stage": "Stone setting",
        "inputGrossWeightG": 20.000,
        "inputNetMetalWeightG": 20.000,
        "outputGrossWeightG": 23.500,
        "outputNetMetalWeightG": 19.700,
        "stoneWeightG": 3.800,
        "alloyWeightG": 0.000,
        "finenessPpt": 750.0,
        "pieces": 2,
        "scaleId": "SC-MICRO-01",
        "operatorName": "Gem Setter Kailash",
        "evidenceRef": "WEIGH-SLIP-09",
        "notes": "38 brilliant-cut diamonds studded",
    })
    assert r.status_code == 201
    m = r.json()
    assert m["inputGrossWeightG"] == 20.0
    assert m["outputGrossWeightG"] == 23.5
    assert m["outputNetMetalWeightG"] == 19.7
    assert m["stoneWeightG"] == 3.8
    assert not m["isSuperseded"]

    # Verify measurements do NOT alter karigar custody balances
    # Karigar should still hold exactly 25.000 g net gold
    head_p = client.get(f"/api/v1/karigars/{w['head']['id']}", headers=h).json()
    assert head_p["custody"]["netWeightG"] == 25.0


def test_superseding_measurement_correction(client, prod_world):
    w = prod_world
    h = w["h"]

    # Initial measurement with scale calibration error
    m1 = client.post("/api/v1/production/measurements", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "stage": "Filing",
        "inputGrossWeightG": 15.000,
        "inputNetMetalWeightG": 15.000,
        "outputGrossWeightG": 14.800,
        "outputNetMetalWeightG": 14.800,
        "finenessPpt": 750.0,
        "pieces": 2,
    }).json()
    assert not m1["isSuperseded"]

    # Correcting measurement (supersedes m1)
    m2_r = client.post("/api/v1/production/measurements", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "stage": "Filing",
        "inputGrossWeightG": 15.000,
        "inputNetMetalWeightG": 15.000,
        "outputGrossWeightG": 14.720,
        "outputNetMetalWeightG": 14.720,
        "finenessPpt": 750.0,
        "pieces": 2,
        "supersedesId": m1["id"],
        "correctionReason": "Re-weighed on calibrated analytical balance SC-CAL-02",
    })
    assert m2_r.status_code == 201
    m2 = m2_r.json()

    # Verify m1 is now marked superseded with reference to m2
    measurements = client.get(f"/api/v1/production/measurements?jobId={w['job']['id']}", headers=h).json()["items"]
    m1_updated = next(item for item in measurements if item["id"] == m1["id"])
    assert m1_updated["isSuperseded"] is True
    assert m1_updated["supersededById"] == m2["id"]
    assert m1_updated["correctionReason"] == "Re-weighed on calibrated analytical balance SC-CAL-02"
