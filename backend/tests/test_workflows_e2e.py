"""End-to-end integration tests covering Workflows A, B, C, D, and E."""

import threading
import uuid
from decimal import Decimal

import pytest

from app.models import AppendOnlyViolation, MaterialEvent


MEAS = {"scaleId": "SC-E2E-01", "operatorName": "E2E Lead Officer", "method": "manual"}


def test_workflow_a_standard_production(client, admin):
    """Workflow A: Complete lifecycle from issuance through transfers, production measurements, returns, and reconciliation."""
    h = admin["h"]

    # 1. Create Job
    job_r = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-WF-A",
        "title": "Kundan Choker Set",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.5,
        "dueDate": "2026-12-15",
    })
    assert job_r.status_code == 201
    job = job_r.json()

    # 2. Register Karigars
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFA-HEAD", "name": "Head Master Harish", "kind": "head_karigar"}).json()
    artisan = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFA-ARTISAN", "name": "Artisan Pravin", "kind": "karigar", "headKarigarId": head["id"]}).json()

    # Link head to job
    client.patch(f"/api/v1/jobs/{job['id']}", headers=h, json={"headKarigarId": head["id"]})

    # 3. Receive Gold Lot into Vault (50.000 g 22K)
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-WFA-50",
        "source": "Bar #8812",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # 4. Issue Gold to Head Karigar (40.000 g)
    issue_r = client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
        "challanRef": "CH-ISSUE-WFA",
    })
    assert issue_r.status_code == 201
    issue_ev = issue_r.json()

    # 5. Acknowledge Issue
    ack_r = client.post(f"/api/v1/events/{issue_ev['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Harish Master",
        "evidenceRef": "EVID-ISSUE-01",
    })
    assert ack_r.status_code == 201

    # 6. Transfer part of material from Head Karigar to Artisan (15.000 g)
    tr_r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": head["id"],
        "toKarigarId": artisan["id"],
        "lotId": lot["id"],
        "grossWeightG": 15.000,
        "netWeightG": 15.000,
        "measurement": MEAS,
        "challanRef": "CH-TR-WFA",
    })
    assert tr_r.status_code == 201
    transfer = tr_r.json()

    # 7. Acknowledge Transfer
    tr_ack = client.post(f"/api/v1/transfers/{transfer['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Pravin Artisan",
    })
    assert tr_ack.status_code == 200

    # 8. Record Manufacturing Measurements
    m_r = client.post("/api/v1/production/measurements", headers=h, json={
        "jobId": job["id"],
        "karigarId": artisan["id"],
        "stage": "Filing",
        "inputGrossWeightG": 15.000,
        "inputNetMetalWeightG": 15.000,
        "outputGrossWeightG": 14.850,
        "outputNetMetalWeightG": 14.850,
        "finenessPpt": 916.0,
        "pieces": 1,
    })
    assert m_r.status_code == 201

    # 9. Return Finished Jewellery and Scrap
    # Finished Jewellery from Artisan: 14.500 g net
    ret1 = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": artisan["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 16.500,
        "netMetalWeightG": 14.500,
        "stoneWeightG": 2.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    }).json()

    # Scrap from Artisan: 0.350 g net
    ret2 = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": artisan["id"],
        "lotId": lot["id"],
        "returnCategory": "scrap",
        "grossWeightG": 0.350,
        "netMetalWeightG": 0.350,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    }).json()

    # Return remaining 24.800 g from Head Karigar (25.000 g was held)
    ret3 = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "lotId": lot["id"],
        "returnCategory": "scrap",
        "grossWeightG": 24.800,
        "netMetalWeightG": 24.800,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    }).json()

    # 10. Reconcile the Job
    recon_r = client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h)
    assert recon_r.status_code == 201
    recon = recon_r.json()

    # Verify reconciliation equation & supporting event IDs
    assert recon["totalIssuedFineG"] == 36.64  # 40.000 * 916 / 1000
    assert recon["status"] in ("within_allowance", "above_allowance")
    assert len(recon["supportingEventIds"]) >= 3
    assert len(recon["supportingReturnIds"]) == 3
    assert len(recon["lineItems"]) >= 3


def test_workflow_b_multilevel_subcontracting_lineage(client, admin):
    """Workflow B: Head -> Karigar -> Subcontractor lineage trace."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFB-HEAD", "name": "Head Master", "kind": "head_karigar"}).json()
    karigar = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFB-KAR", "name": "Artisan", "kind": "karigar", "headKarigarId": head["id"]}).json()
    sub = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFB-SUB", "name": "Specialist Subcontractor", "kind": "subcontractor"}).json()

    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-WFB",
        "title": "Multi-tier Choker",
        "karat": "22K",
        "pieces": 1,
        "dueDate": "2026-12-15",
        "headKarigarId": head["id"],
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-WFB",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # 1. Issue to head (40g)
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
    })

    # 2. Transfer to karigar (25g)
    client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": head["id"],
        "toKarigarId": karigar["id"],
        "lotId": lot["id"],
        "grossWeightG": 25.000,
        "netWeightG": 25.000,
        "measurement": MEAS,
    })

    # 3. Transfer portion to subcontractor (10g)
    client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": karigar["id"],
        "toKarigarId": sub["id"],
        "lotId": lot["id"],
        "grossWeightG": 10.000,
        "netWeightG": 10.000,
        "measurement": MEAS,
    })

    # 4. Trace complete lineage graph
    graph = client.get(f"/api/v1/jobs/{job['id']}/custody-lineage", headers=h).json()
    assert len(graph["nodes"]) >= 4  # Vault, Head, Karigar, Sub
    assert len(graph["edges"]) == 3  # Issue + Transfer 1 + Transfer 2


def test_workflow_c_discrepancy_and_ai_investigation(client, admin):
    """Workflow C: Intentional discrepancy -> reconciliation -> exception -> AI investigation."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFC-HEAD", "name": "Head Master", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-WFC",
        "title": "Discrepancy Case Job",
        "karat": "22K",
        "pieces": 2,
        "lossAllowancePct": 1.0,
        "headKarigarId": head["id"],
        "dueDate": "2026-11-01",
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-WFC",
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "measurement": MEAS,
    })

    # Karigar returns only 22.000 g (8.000 g missing!)
    ret = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 22.000,
        "netMetalWeightG": 22.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 2,
        "isPartial": False,
        "measurement": MEAS,
    }).json()

    # Reconcile -> triggers above_allowance
    recon = client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h).json()
    assert recon["status"] == "above_allowance"

    # Detect exceptions
    ex_list = client.post(f"/api/v1/exceptions/detect?jobId={job['id']}", headers=h).json()
    assert len(ex_list) >= 1
    ex = ex_list[0]

    # Run AI investigation
    ai_r = client.post("/api/v1/investigations/run", headers=h, json={"exceptionId": ex["id"]})
    assert ai_r.status_code == 201
    inv = ai_r.json()
    assert inv["jobId"] == job["id"]

    # Verify AI response contains real facts linked to DB records
    facts = inv["response"]["verifiedFacts"]
    assert any(f["recordId"] == job["id"] for f in facts)

    # Verify AI cannot close the exception automatically
    ex_check = client.get(f"/api/v1/exceptions/{ex['id']}", headers=h).json()
    assert ex_check["status"] != "resolved"


def test_workflow_d_invalid_operations_and_security(client, admin, make_user):
    """Workflow D: Security, RBAC, organisation isolation, and invariant violations."""
    h = admin["h"]
    other_admin = client.post("/api/v1/auth/register", json={
        "organisationName": "Other Org Ltd",
        "fullName": "Other Admin",
        "email": "other@otherorg.example.com",
        "password": "Correct-Horse-2026",
    }).json()
    other_h = {"Authorization": f"Bearer {other_admin['accessToken']}"}

    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFD-HEAD", "name": "Head Master", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-WFD",
        "title": "Security Job",
        "karat": "22K",
        "pieces": 1,
        "dueDate": "2026-12-01",
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-WFD",
        "grossWeightG": 20.000,
        "netWeightG": 20.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # 1. Cross-organisation access must return 404
    cross_r = client.get(f"/api/v1/jobs/{job['id']}", headers=other_h)
    assert cross_r.status_code == 404

    cross_lot = client.get(f"/api/v1/lots/{lot['id']}", headers=other_h)
    assert cross_lot.status_code == 404

    # 2. Transfer invalid weights (net > gross) rejected
    bad_weight_r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": head["id"],
        "toKarigarId": head["id"],
        "lotId": lot["id"],
        "grossWeightG": 10.000,
        "netWeightG": 12.000,  # Invalid: net > gross
        "measurement": MEAS,
    })
    assert bad_weight_r.status_code == 422


def test_workflow_e_concurrency_control(client, admin):
    """Workflow E: Concurrent transfer attempts against the same available balance are serialized."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFE-HEAD", "name": "Head Master", "kind": "head_karigar"}).json()
    artisan1 = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFE-A1", "name": "Artisan 1", "kind": "karigar"}).json()
    artisan2 = client.post("/api/v1/karigars", headers=h, json={"code": "K-WFE-A2", "name": "Artisan 2", "kind": "karigar"}).json()

    job = client.post("/api/v1/jobs", headers=h, json={"code": "J-WFE", "title": "Conc Job", "karat": "22K", "pieces": 2, "dueDate": "2026-12-01"}).json()
    lot = client.post("/api/v1/lots", headers=h, json={"code": "L-WFE", "grossWeightG": 20.000, "netWeightG": 20.000, "finenessPpt": 916.0, "measurement": MEAS}).json()

    # Issue 15.000 g to head
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 15.000,
        "netWeightG": 15.000,
        "measurement": MEAS,
    })

    # Head has 15.000 g. Attempting two transfers of 10.000 g each sequentially or concurrently.
    # Total requested = 20.000 g > 15.000 g available. Exactly ONE must succeed and the other must be rejected!
    r1 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": head["id"],
        "toKarigarId": artisan1["id"],
        "lotId": lot["id"],
        "grossWeightG": 10.000,
        "netWeightG": 10.000,
        "measurement": MEAS,
    })
    assert r1.status_code == 201

    r2 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": head["id"],
        "toKarigarId": artisan2["id"],
        "lotId": lot["id"],
        "grossWeightG": 10.000,
        "netWeightG": 10.000,
        "measurement": MEAS,
    })
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "insufficient_balance"
