"""Tests for commercial settlement rules, worksheets, and approval workflow."""

import pytest


MEAS = {"scaleId": "SC-SETTLE-01", "operatorName": "Settlement Desk", "method": "manual"}


@pytest.fixture()
def settle_world(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-SETTLE-01", "name": "Bhikaji Master", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-SETTLE-JOB",
        "title": "Choker Necklace",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.5,
        "headKarigarId": head["id"],
        "dueDate": "2026-12-25",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-SETTLE-BAR",
        "source": "916 Bar",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Issue 40.000 g
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
    })

    # Return 35.000 g finished jewellery and 4.000 g scrap
    # Total returned: 39.000 g; 1.000 g loss.
    # Allowance on 40.000 * 916 / 1000 = 36.640 g fine:
    # 1.5% allowance = 0.550 g fine.
    # Actual loss = 40.000 - 39.000 = 1.000 g net = 0.916 g fine.
    # Excess loss = 0.916 - 0.550 = 0.366 g fine!
    client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 35.000,
        "netMetalWeightG": 35.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    })
    client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "lotId": lot["id"],
        "returnCategory": "scrap",
        "grossWeightG": 4.000,
        "netMetalWeightG": 4.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # Run reconciliation
    recon = client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h).json()

    # Create settlement rule: Labour ₹500/g, gold rate ₹7500/g
    rule = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-CHOKER",
        "name": "Standard Choker Contract 2026",
        "karat": "22K",
        "labourRatePerG": 500.0,
        "lossAllowancePct": 1.5,
        "goldRatePerFineG": 7500.0,
        "effectiveFrom": "2026-01-01",
    }).json()

    return {"h": h, "head": head, "job": job, "lot": lot, "recon": recon, "rule": rule}


def test_settlement_worksheet_calculation_and_approval(client, settle_world, make_user):
    w = settle_world
    h = w["h"]
    viewer = make_user("viewer", "viewer@example.com")

    # 1. Generate worksheet
    r = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "settlementRuleId": w["rule"]["id"],
        "approvedDeductions": 250.0,
        "notes": "Fast-track completion bonus waived per SLA",
    })
    assert r.status_code == 201
    sheet = r.json()
    assert sheet["status"] == "draft"

    # Labour: 35.000 g finished × ₹500/g = ₹17,500
    assert sheet["finishedGrossG"] == 35.0
    assert sheet["labourAmount"] == 17500.0

    # Excess loss: ~0.366 g × ₹7500 = ~₹2,745
    assert sheet["excessLossFineG"] == 0.366
    assert sheet["goldRecoveryAmount"] == 2745.0

    # Net payable: 17,500 - 2,745 - 250 = ₹14,505
    assert sheet["netPayableAmount"] == 14505.0

    # 2. Submit worksheet
    sub_r = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/submit", headers=h)
    assert sub_r.status_code == 200
    assert sub_r.json()["status"] == "submitted"

    # 3. Viewer cannot approve worksheet (RBAC guard)
    fail_app = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/approve", headers=viewer["h"], json={})
    assert fail_app.status_code == 403

    # 4. Manager approves worksheet
    ok_app = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/approve", headers=h, json={
        "notes": "Approved for accounts payout batch #41",
    })
    assert ok_app.status_code == 200
    approved = ok_app.json()
    assert approved["status"] == "approved"
    assert approved["approvedAt"] is not None

    # Job status updated to settled
    job = client.get(f"/api/v1/jobs/{w['job']['id']}", headers=h).json()
    assert job["status"] == "settled"


def test_settlement_rejection(client, settle_world):
    w = settle_world
    h = w["h"]

    sheet = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": w["job"]["id"],
    }).json()

    # Rejection requires reason
    fail_rej = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/reject", headers=h, json={"reason": ""})
    assert fail_rej.status_code == 422

    ok_rej = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/reject", headers=h, json={
        "reason": "Excessive stone damage deduction needs audit",
    })
    assert ok_rej.status_code == 200
    assert ok_rej.json()["status"] == "rejected"
    assert ok_rej.json()["rejectionReason"] == "Excessive stone damage deduction needs audit"
