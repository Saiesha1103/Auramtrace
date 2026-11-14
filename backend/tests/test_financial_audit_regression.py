"""Regression tests for financial calculations, dual loss allowances, and fire assay reconciliation."""

from decimal import Decimal
import pytest


MEAS = {"scaleId": "SC-FIN-01", "operatorName": "Assay & Audit Officer", "method": "manual"}


@pytest.fixture()
def financial_audit_world(client, admin):
    """Provisions a clean, isolated world for testing financial calculations and reconciliation."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-AUD-01",
        "name": "Audit Master Craftsman",
        "kind": "head_karigar",
    }).json()

    # Job Order created with manufacturing engineering tolerance of 1.2%
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-AUD-01",
        "title": "Heritage Bridal Choker",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.2,
        "headKarigarId": head["id"],
        "dueDate": "2026-12-30",
    }).json()

    # Bullion lot intake: 50.000 g @ 916.0 ppt
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-AUD-916",
        "source": "Certified 916 Bullion Bar",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Issue 40.000 g gross / net metal to head karigar
    # Fine gold issued = 40.000 * 916 / 1000 = 36.640 g fine gold
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
    })

    return {"h": h, "head": head, "job": job, "lot": lot}


def test_dual_loss_allowance_job_vs_settlement_rule(client, financial_audit_world):
    """Verifies Issue A:
    1. JobOrder.loss_allowance_pct (1.2%) governs physical manufacturing reconciliation tolerance.
    2. SettlementRule.loss_allowance_pct (1.5%) governs commercial financial settlement recovery.
    3. The settlement worksheet must NOT blindly copy the job's allowance when a rule specifies its own.
    """
    w = financial_audit_world
    h = w["h"]

    # Returns: 24.500 g finished jewellery + 14.850 g scrap = 39.350 g total returned
    # Physical loss = 40.000 - 39.350 = 0.650 g gross/net = 0.650 * 0.916 = 0.5954 -> 0.595 g fine gold
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 24.500,
        "netMetalWeightG": 24.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    })
    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 14.850,
        "netMetalWeightG": 14.850,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # 1. Run physical manufacturing reconciliation:
    # Issued: 36.640 g fine.
    # Job engineering tolerance: 1.2% -> 36.640 * 0.012 = 0.43968 -> 0.440 g fine gold allowance.
    recon = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h).json()
    assert recon["totalIssuedFineG"] == 36.64
    assert recon["lossAllowancePct"] == 1.2
    assert recon["lossAllowanceFineG"] == 0.440
    assert recon["unexplainedVarianceFineG"] == 0.595
    # Since 0.595 g > 0.440 g, reconciliation correctly flags above_allowance
    assert recon["status"] == "above_allowance"

    # 2. Create Commercial Settlement Rule with agreed karigar contractual allowance of 1.5%
    # Labour ₹450/g, Gold rate ₹7,000/fine gram
    rule = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-AUDIT-22K",
        "name": "Commercial Master Artisan Rule",
        "karat": "22K",
        "labourRatePerG": 450.0,
        "lossAllowancePct": 1.5,
        "goldRatePerFineG": 7000.0,
        "effectiveFrom": "2026-01-01",
    }).json()
    assert rule["lossAllowancePct"] == 1.5

    # 3. Generate commercial settlement worksheet referencing the rule:
    # Contractual allowance for settlement must be:
    # 36.640 g * 1.5% = 0.5496 -> 0.550 g fine gold (NOT 0.440 g from the job!)
    # Excess loss = 0.595 g actual loss - 0.550 g contractual allowance = 0.045 g fine gold!
    # Recovery amount = 0.045 g * ₹7,000 = ₹315.00
    # Labour amount = 24.500 g * ₹450 = ₹11,025.00
    # Net payable = 11,025.00 - 315.00 = ₹10,710.00
    sheet = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "settlementRuleId": rule["id"],
        "approvedDeductions": 0.0,
    }).json()

    assert sheet["finishedGrossG"] == 24.5
    assert sheet["labourAmount"] == 11025.0
    assert sheet["wastageAllowanceFineG"] == 0.550, "Settlement must use rule's 1.5% allowance (0.550 g), not job's 1.2% (0.440 g)"
    assert sheet["actualLossFineG"] == 0.595
    assert sheet["excessLossFineG"] == 0.045
    assert sheet["goldRecoveryAmount"] == 315.0
    assert sheet["netPayableAmount"] == 10710.0


def test_fire_assay_superseding_and_immutable_reconciliation_snapshots(client, financial_audit_world):
    """Verifies Issue B:
    1. Return initially created with declared 916.0 ppt fineness.
    2. Initial reconciliation snapshot (Run #1) records declared fine gold.
    3. Laboratory fire assay records verified 890.0 ppt (26.0 ppt deficit).
    4. Return fine_gold_g is updated to assayed value; declared fineness is preserved.
    5. Revised reconciliation (Run #2) marks Run #1 as is_latest=False while preserving all historical Run #1 data.
    6. Run #2 unexplained variance correctly equals physical loss + assay deficit (0.774 g).
    7. Exceptions and settlements use authoritative Run #2 without double-counting the assay deficit.
    """
    w = financial_audit_world
    h = w["h"]

    # Step A: Return finished jewellery (24.500 g net) and scrap (14.850 g net)
    # Total net metal = 39.350 g (0.650 g physical loss)
    # Plus Harish retained scrap 0.500 g -> total metal accounted = 39.850 g (physical loss = 0.150 g net = 0.137 g fine)
    ret_fg = client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 24.500,
        "netMetalWeightG": 24.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    }).json()

    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 0.500,
        "netMetalWeightG": 0.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": True,
        "measurement": MEAS,
    })

    client.post("/api/v1/returns", headers=h, json={
        "jobId": w["job"]["id"],
        "karigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "returnCategory": "scrap",
        "grossWeightG": 14.850,
        "netMetalWeightG": 14.850,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # Step B: Initial Reconciliation Snapshot (Run #1) before laboratory assay
    # Issued: 36.640 g fine.
    # Finished: 24.500 * 0.916 = 22.442 g fine.
    # Scrap: (0.500 + 14.850) * 0.916 = 14.0606 -> 14.061 g fine.
    # Accounted: 22.442 + 14.061 = 36.503 g fine.
    # Unexplained variance: 36.640 - 36.503 = 0.137 g fine.
    recon_v1 = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h).json()
    assert recon_v1["runNumber"] == 1
    assert recon_v1["isLatest"] is True
    assert recon_v1["finishedJewelleryFineG"] == 22.442
    assert recon_v1["returnedScrapFineG"] == 14.061
    assert recon_v1["actualAccountedFineG"] == 36.503
    assert recon_v1["unexplainedVarianceFineG"] == 0.137
    assert recon_v1["status"] == "within_allowance"

    # Step C: Laboratory Fire Assay verification
    # Declared: 916.0 ppt, Assayed: 890.0 ppt (26.0 ppt deficit)
    # Expected fine gold reduction: 24.500 * (916 - 890) / 1000 = 0.637 g fine gold deficit
    # New finished fine gold: 24.500 * 890 / 1000 = 21.805 g
    assay_res = client.post(f"/api/v1/returns/{ret_fg['id']}/assay", headers=h, json={
        "assayedFinenessPpt": 890.0,
        "assayEvidenceRef": "XRF-CERT-LAB-99",
        "notes": "Verified fire assay confirms 890.0 ppt (26 ppt shortfall)",
    }).json()
    assert assay_res["declaredFinenessPpt"] == 916.0
    assert assay_res["assayedFinenessPpt"] == 890.0
    assert assay_res["fineGoldG"] == 21.805

    # Step D: Revised Reconciliation Snapshot (Run #2)
    # Total Accounted Fine: 21.805 (finished) + 14.061 (scrap) = 35.866 g
    # Total Issued Fine: 36.640 g
    # Unexplained Variance: 36.640 - 35.866 = 0.774 g fine gold!
    # Physical Loss (0.137 g) + Assay Deficit (0.637 g) = exactly 0.774 g!
    recon_v2 = client.post(f"/api/v1/jobs/{w['job']['id']}/reconcile", headers=h).json()
    assert recon_v2["runNumber"] == 2
    assert recon_v2["isLatest"] is True
    assert recon_v2["finishedJewelleryFineG"] == 21.805
    assert recon_v2["returnedScrapFineG"] == 14.061
    assert recon_v2["actualAccountedFineG"] == 35.866
    assert recon_v2["unexplainedVarianceFineG"] == 0.774
    # Status flags fineness_mismatch due to >= 20.0 ppt deficit
    assert recon_v2["status"] == "fineness_mismatch"

    # Step E: Verify Immutability of Historical Snapshot Run #1
    recons_list = client.get(f"/api/v1/reconciliations?jobId={w['job']['id']}", headers=h).json()
    runs_by_num = {r["runNumber"]: r for r in recons_list["items"]}
    assert runs_by_num[1]["isLatest"] is False
    assert runs_by_num[1]["unexplainedVarianceFineG"] == 0.137, "Historical Run #1 variance must remain immutable"
    assert runs_by_num[1]["finishedJewelleryFineG"] == 22.442, "Historical Run #1 finished fine must remain immutable"
    assert runs_by_num[2]["isLatest"] is True
    assert runs_by_num[2]["unexplainedVarianceFineG"] == 0.774

    # Step F: Exception Detection uses latest snapshot (Run #2)
    exceptions = client.post(f"/api/v1/exceptions/detect?jobId={w['job']['id']}", headers=h).json()
    exc_map = {e["exceptionType"]: e for e in exceptions}

    # Variance exception based on Run #2 (0.774 g variance vs 0.440 g allowance = 0.334 g excess)
    assert "variance" in exc_map
    assert exc_map["variance"]["observedValue"] == "0.774 g fine"
    assert exc_map["variance"]["varianceAmountG"] == 0.334

    # Purity mismatch exception identifies exact 0.637 g deficit
    assert "purity_mismatch" in exc_map
    assert exc_map["purity_mismatch"]["varianceAmountG"] == 0.637

    # Step G: Settlement Worksheet uses authoritative Run #2 without double-counting
    # Labour on 24.500 g @ ₹450 = ₹11,025.00
    # Rule allowance 1.5% = 0.550 g
    # Actual loss = 0.774 g
    # Excess loss = 0.774 - 0.550 = 0.224 g
    # Recovery = 0.224 * ₹6,800 = ₹1,523.20
    # Net payable = 11,025.00 - 1,523.20 = ₹9,501.80
    rule = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-AUDIT-GOLD",
        "name": "Audit Settlement Contract",
        "karat": "22K",
        "labourRatePerG": 450.0,
        "lossAllowancePct": 1.5,
        "goldRatePerFineG": 6800.0,
        "effectiveFrom": "2026-01-01",
    }).json()

    sheet = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": w["job"]["id"],
        "settlementRuleId": rule["id"],
    }).json()

    assert sheet["actualLossFineG"] == 0.774
    assert sheet["wastageAllowanceFineG"] == 0.550
    assert sheet["excessLossFineG"] == 0.224
    assert sheet["goldRecoveryAmount"] == 1523.2
    assert sheet["netPayableAmount"] == 9501.8
