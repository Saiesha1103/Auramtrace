"""Kalyan Heritage Goldsmiths End-to-End Acceptance Test.

Simulates the complete production lifecycle, multi-level hierarchy,
reconciliation snapshots before/after fire assay, exception detection,
and commercial settlement calculation with exact rupee and milligram verification.
"""

from decimal import Decimal
import pytest


MEAS = {"scaleId": "SC-KALYAN-01", "operatorName": "Kalyan Vault Officer", "method": "manual"}


def test_kalyan_production_lifecycle_acceptance(client, admin):
    """Executes the full Kalyan Heritage Goldsmiths production and financial scenario."""
    h = admin["h"]

    # 1. Karigar Hierarchy: Rajesh Soni (Head Karigar) and Harish Verma (Filigree Artisan)
    rajesh = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-RAJESH-01",
        "name": "Rajesh Soni",
        "kind": "head_karigar",
    }).json()

    harish = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-HARISH-01",
        "name": "Harish Verma",
        "kind": "karigar",
        "headKarigarId": rajesh["id"],
    }).json()

    # 2. Bullion Intake: 50.000 g @ 916.0 ppt (22K)
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-KALYAN-916",
        "source": "MMTC-PAMP Certified 916 Bar",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # 3. Job Order: J-2026-03-001 (Bridal Choker, 1 piece, loss allowance 1.2%)
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-2026-03-001",
        "title": "Kalyan Heritage Bridal Choker",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.2,
        "headKarigarId": rajesh["id"],
        "dueDate": "2026-12-31",
    }).json()

    # 4. Issue 40.000 g gold to Rajesh on Job J-2026-03-001
    # Total fine gold issued = 40.000 * 0.916 = 36.640 g fine
    issue_ev = client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": rajesh["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
        "challanRef": "CH-KALYAN-001",
    }).json()

    # Acknowledge issuance
    client.post(f"/api/v1/events/{issue_ev['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Rajesh Soni",
    })

    # 5. Rajesh transfers 15.000 g to Harish for filigree work
    tr1 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": rajesh["id"],
        "toKarigarId": harish["id"],
        "lotId": lot["id"],
        "grossWeightG": 15.000,
        "netWeightG": 15.000,
        "measurement": MEAS,
        "challanRef": "TR-RAJ-HAR-01",
    }).json()

    # Harish acknowledges receipt of 15.000 g
    client.post(f"/api/v1/transfers/{tr1['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Harish Verma",
    })

    # 6. Harish records filigree production: 14.500 g net metal (input 15.000 g)
    client.post("/api/v1/production/measurements", headers=h, json={
        "jobId": job["id"],
        "karigarId": harish["id"],
        "stage": "Filigree Shaping",
        "inputGrossWeightG": 15.000,
        "inputNetMetalWeightG": 15.000,
        "outputGrossWeightG": 14.500,
        "outputNetMetalWeightG": 14.500,
        "finenessPpt": 916.0,
        "pieces": 1,
    })

    # 7. Harish returns 0.500 g scrap (declared 916.0 ppt)
    ret_harish_scrap = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": harish["id"],
        "lotId": lot["id"],
        "returnCategory": "scrap",
        "grossWeightG": 0.500,
        "netMetalWeightG": 0.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    }).json()

    # 8. Harish transfers 14.500 g WIP back to Rajesh for final assembly
    tr2 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": job["id"],
        "fromKarigarId": harish["id"],
        "toKarigarId": rajesh["id"],
        "lotId": lot["id"],
        "grossWeightG": 14.500,
        "netWeightG": 14.500,
        "measurement": MEAS,
        "challanRef": "TR-HAR-RAJ-01",
    }).json()

    # Rajesh acknowledges receipt of the filigree component
    client.post(f"/api/v1/transfers/{tr2['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Rajesh Soni",
    })

    # 9. Rajesh completes assembly and returns:
    # 24.500 g Finished Jewellery (declared 916 ppt, pieces=1)
    ret_finished = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": rajesh["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 24.500,
        "netMetalWeightG": 24.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    }).json()

    # 14.850 g Scrap returned by Rajesh (declared 916 ppt)
    ret_rajesh_scrap = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": rajesh["id"],
        "lotId": lot["id"],
        "returnCategory": "scrap",
        "grossWeightG": 14.850,
        "netMetalWeightG": 14.850,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    }).json()

    # 10. Initial Reconciliation (Run #1) BEFORE Laboratory Assay
    # Metal Accounted:
    # Finished jewellery: 24.500 * 0.916 = 22.442 g fine
    # Scrap: (0.500 + 14.850) * 0.916 = 14.0606 -> 14.061 g fine
    # Total accounted fine: 22.442 + 14.061 = 36.503 g fine
    # Total issued fine: 40.000 * 0.916 = 36.640 g fine
    # Unexplained variance: 36.640 - 36.503 = 0.137 g fine gold
    # Engineering loss allowance: 36.640 * 1.2% = 0.43968 -> 0.440 g fine gold
    recon_v1 = client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h).json()
    assert recon_v1["runNumber"] == 1
    assert recon_v1["isLatest"] is True
    assert recon_v1["totalIssuedFineG"] == 36.640
    assert recon_v1["finishedJewelleryFineG"] == 22.442
    assert recon_v1["returnedScrapFineG"] == 14.061
    assert recon_v1["actualAccountedFineG"] == 36.503
    assert recon_v1["lossAllowanceFineG"] == 0.440
    assert recon_v1["unexplainedVarianceFineG"] == 0.137
    assert recon_v1["status"] == "within_allowance"

    # 11. Laboratory Fire Assay Verification:
    # Finished jewellery assayed at 890.0 ppt (26.0 ppt deficit)
    # Harish scrap assayed at 916.0 ppt (0 deficit)
    # Rajesh scrap assayed at 916.0 ppt (0 deficit)
    client.post(f"/api/v1/returns/{ret_finished['id']}/assay", headers=h, json={
        "assayedFinenessPpt": 890.0,
        "assayEvidenceRef": "KALYAN-LAB-ASSAY-01",
        "notes": "Fire assay confirms 890.0 ppt (shortfall of 26.0 ppt)",
    })
    client.post(f"/api/v1/returns/{ret_harish_scrap['id']}/assay", headers=h, json={
        "assayedFinenessPpt": 916.0,
        "assayEvidenceRef": "KALYAN-LAB-ASSAY-02",
        "notes": "Verified 916.0 ppt",
    })
    client.post(f"/api/v1/returns/{ret_rajesh_scrap['id']}/assay", headers=h, json={
        "assayedFinenessPpt": 916.0,
        "assayEvidenceRef": "KALYAN-LAB-ASSAY-03",
        "notes": "Verified 916.0 ppt",
    })

    # 12. Revised Reconciliation (Run #2) AFTER Laboratory Assay
    # Finished fine: 24.500 * 0.890 = 21.805 g fine (loss of 0.637 g fine)
    # Scrap fine: 14.061 g fine
    # Total accounted fine: 21.805 + 14.061 = 35.866 g fine
    # Total issued fine: 36.640 g fine
    # Unexplained variance: 36.640 - 35.866 = 0.774 g fine gold!
    # Physical filing loss (0.137 g) + Assay deficit (0.637 g) = exactly 0.774 g!
    recon_v2 = client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h).json()
    assert recon_v2["runNumber"] == 2
    assert recon_v2["isLatest"] is True
    assert recon_v2["finishedJewelleryFineG"] == 21.805
    assert recon_v2["returnedScrapFineG"] == 14.061
    assert recon_v2["actualAccountedFineG"] == 35.866
    assert recon_v2["unexplainedVarianceFineG"] == 0.774
    assert recon_v2["status"] == "fineness_mismatch"

    # Verify Historical Run #1 Immutability
    recon_history = client.get(f"/api/v1/reconciliations?jobId={job['id']}", headers=h).json()
    runs = {r["runNumber"]: r for r in recon_history["items"]}
    assert runs[1]["isLatest"] is False
    assert runs[1]["unexplainedVarianceFineG"] == 0.137
    assert runs[1]["finishedJewelleryFineG"] == 22.442
    assert runs[2]["isLatest"] is True
    assert runs[2]["unexplainedVarianceFineG"] == 0.774

    # 13. Exception Detection:
    # Detects variance (0.774 g vs 0.440 g allowance = 0.334 g excess)
    # Detects purity mismatch (26.0 ppt shortfall on 24.500 g = 0.637 g fine deficit)
    exceptions = client.post(f"/api/v1/exceptions/detect?jobId={job['id']}", headers=h).json()
    exc_by_type = {e["exceptionType"]: e for e in exceptions}

    assert "variance" in exc_by_type
    assert exc_by_type["variance"]["observedValue"] == "0.774 g fine"
    assert exc_by_type["variance"]["varianceAmountG"] == 0.334

    assert "purity_mismatch" in exc_by_type
    assert exc_by_type["purity_mismatch"]["varianceAmountG"] == 0.637
    assert exc_by_type["purity_mismatch"]["expectedValue"] == "916.0 ppt"
    assert exc_by_type["purity_mismatch"]["observedValue"] == "890.0 ppt"

    # 14. Commercial Settlement Calculation:
    # Contractual rule with 1.5% allowance, ₹7,250/fine g gold rate, ₹450/g making charges
    rule = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-KALYAN-22K",
        "name": "Kalyan Master Craftsman Agreement",
        "karat": "22K",
        "labourRatePerG": 450.0,
        "lossAllowancePct": 1.5,
        "goldRatePerFineG": 7250.0,
        "effectiveFrom": "2026-01-01",
    }).json()

    # Create Accounts Manager for separation of duties (four-eyes principle)
    mgr_user = client.post("/api/v1/users", headers=h, json={
        "email": "kalyan_manager@example.com",
        "fullName": "Kalyan Accounts Manager",
        "role": "manager",
        "password": "Password-123456!",
    }).json()
    mgr_token = client.post("/api/v1/auth/login", json={
        "email": "kalyan_manager@example.com",
        "password": "Password-123456!",
    }).json()["accessToken"]
    mgr_h = {"Authorization": f"Bearer {mgr_token}", "Content-Type": "application/json"}

    # Generate settlement worksheet for Rajesh created by Manager:
    sheet = client.post("/api/v1/settlements/worksheets", headers=mgr_h, json={
        "jobId": job["id"],
        "karigarId": rajesh["id"],
        "settlementRuleId": rule["id"],
        "approvedDeductions": 0.0,
    }).json()

    # Verification of every financial line item:
    # 1. Gross making charges: 24.500 g * ₹450 = ₹11,025.00
    assert sheet["finishedGrossG"] == 24.500
    assert sheet["labourRateApplied"] == 450.0
    assert sheet["labourAmount"] == 11025.00

    # 2. Contractual loss allowance fine: 36.640 g * 1.5% = 0.5496 -> 0.550 g fine
    assert sheet["wastageAllowanceFineG"] == 0.550

    # 3. Actual loss fine: 0.774 g fine
    assert sheet["actualLossFineG"] == 0.774

    # 4. Recoverable excess loss: 0.774 g - 0.550 g = 0.224 g fine
    assert sheet["excessLossFineG"] == 0.224

    # 5. Excess loss deduction: 0.224 g * ₹7,250/g = ₹1,624.00
    assert sheet["goldRateApplied"] == 7250.0
    assert sheet["goldRecoveryAmount"] == 1624.00

    # 6. Net payable to Rajesh: ₹11,025.00 - ₹1,624.00 = ₹9,401.00
    assert sheet["netPayableAmount"] == 9401.00
    assert sheet["status"] == "draft"

    # 15. Worksheet Submission and Approval Lifecycle:
    # Direct approval of draft worksheet must fail (cannot jump draft -> approved)
    fail_draft = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/approve", headers=h, json={})
    assert fail_draft.status_code == 422
    assert fail_draft.json()["error"]["code"] == "invalid_status"

    # Manager submits worksheet
    sub = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/submit", headers=mgr_h).json()
    assert sub["status"] == "submitted"

    # Self-approval by creator (Manager) must fail with 403 (four-eyes principle)
    fail_self = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/approve", headers=mgr_h, json={})
    assert fail_self.status_code == 403
    assert fail_self.json()["error"]["code"] == "self_approval_forbidden"

    # Admin approves worksheet (authorized secondary approver)
    app = client.post(f"/api/v1/settlements/worksheets/{sheet['id']}/approve", headers=h, json={
        "notes": "Approved by Chief Goldsmith Accountant after reviewing fire assay report.",
    }).json()
    assert app["status"] == "approved"

    # Verify Job Status transitioned to 'settled'
    job_refreshed = client.get(f"/api/v1/jobs/{job['id']}", headers=h).json()
    assert job_refreshed["status"] == "settled"
