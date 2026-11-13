"""Tests for fine-gold reconciliation engine and immutable snapshots."""

from decimal import Decimal
import pytest


MEAS = {"scaleId": "SC-RECON-01", "operatorName": "Reconciliation Officer", "method": "manual"}


@pytest.fixture()
def recon_world(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-REC-01", "name": "Mohan Artisan", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-BANGLES",
        "title": "Set of 4 Gold Bangles",
        "karat": "22K",
        "pieces": 4,
        "lossAllowancePct": 1.0,  # 1.0% contractual loss allowance
        "headKarigarId": head["id"],
        "dueDate": "2026-12-10",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-BAR-40",
        "source": "916 Bar",
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Issue 30.000 g 22K (Fine = 30.000 * 916.0 / 1000 = 27.480 g)
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "measurement": MEAS,
    })

    return {"h": h, "head": head, "job": job, "lot": lot}


def test_reconciliation_within_allowance(client, recon_world):
    w = recon_world
    h = w["h"]

    # Karigar returns:
    # 1. Finished Jewellery: 25.000 g @ 916 (Fine = 22.900 g)
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 25.000,
        "netMetalWeightG": 25.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 4,
        "isPartial": True,
        "measurement": MEAS,
    })

    # 2. Scrap: 4.800 g @ 916 (Fine = 4.397 g)
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 4.800,
        "netMetalWeightG": 4.800,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # Issued: 30.000 g -> 27.480 g fine
    # Finished: 25.000 g -> 22.900 g fine
    # Scrap: 4.800 g -> 4.397 g fine
    # Accounted: 22.900 + 4.397 = 27.297 g fine
    # Unexplained variance = 27.480 - 27.297 = 0.183 g fine
    # 1.0% Allowance on 27.480 = 0.275 g fine
    # Since 0.183 <= 0.275, reconciliation status is 'within_allowance'!

    r = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h)
    assert r.status_code == 201
    recon = r.json()

    assert recon["status"] == "within_allowance"
    assert recon["totalIssuedFineG"] == 27.48
    assert recon["finishedJewelleryFineG"] == 22.9
    assert recon["returnedScrapFineG"] == 4.397
    assert recon["unexplainedVarianceFineG"] == 0.183
    assert recon["lossAllowanceFineG"] == 0.275
    assert len(recon["lineItems"]) >= 2

    # Job status updated to reconciled
    job = client.get(f"/api/v1/jobs/{w['job']['id']}", headers=h).json()
    assert job["status"] == "reconciled"


def test_reconciliation_above_allowance(client, recon_world):
    w = recon_world
    h = w["h"]

    # Karigar returns only 20.000 g finished jewellery and 5.000 g scrap (total 25.000 g from 30.000 g)
    # 5.000 g is missing! Variance exceeds 1% allowance!
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 20.000,
        "netMetalWeightG": 20.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 3,
        "isPartial": False,
        "measurement": MEAS,
    })

    r = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h)
    assert r.status_code == 201
    recon = r.json()
    assert recon["status"] == "above_allowance"
    assert recon["unexplainedVarianceFineG"] > recon["lossAllowanceFineG"]


def test_reconciliation_summary_and_compare(client, recon_world):
    w = recon_world
    h = w["h"]

    r1 = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h).json()

    # Log an additional return
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 5.000,
        "netMetalWeightG": 5.000,
        "declaredFinenessPpt": 916.0,
        "measurement": MEAS,
    })

    r2 = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h).json()

    # Compare runs
    cmp_r = client.get(f"/api/v1/reconciliations/compare?run1Id={r1['id']}&run2Id={r2['id']}", headers=h)
    assert cmp_r.status_code == 200
    comp = cmp_r.json()
    assert "delta" in comp
    assert comp["delta"]["accountedFineG"] > 0

    # Summary
    summary = client.get("/api/v1/reconciliations/summary", headers=h).json()
    assert summary["totalJobs"] >= 1
    assert summary["totalIssuedFineG"] >= 27.48
