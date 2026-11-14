"""Comprehensive regression tests for pre-release audit fixes:

1. Exception code uniqueness and collision prevention across jobs.
2. Settlement rule selection using job karat and effective date matching.
3. Approval controls:
   - Draft cannot be approved directly (invalid_status 422).
   - Creator cannot approve own worksheet (four-eyes principle 403).
   - Unauthorized role cannot approve (403).
   - Legitimate secondary approver succeeds (200).
4. Monetary value rounding to ₹0.01 (paise precision).
5. User password rotation via PATCH /users/{id}.
"""

from datetime import date, datetime, UTC
from decimal import Decimal
import pytest


MEAS = {"scaleId": "SC-AUDIT-01", "operatorName": "Audit Lead", "method": "manual"}


def test_exception_code_collision_prevention_across_jobs(client, admin):
    """Verifies that two jobs with identical prefix or similar codes do NOT collide,

    overwrite each other, or fail with duplicate_code in PostgreSQL.
    """
    h = admin["h"]

    k = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-COL-01",
        "name": "Collision Test Artisan",
        "kind": "head_karigar",
    }).json()

    # Job 1 and Job 2 have long, almost identical codes
    job1 = client.post("/api/v1/jobs", headers=h, json={
        "code": "JOB-LONG-PREFIX-0001",
        "title": "Batch A Choker",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.0,
        "headKarigarId": k["id"],
        "dueDate": "2026-12-30",
    }).json()

    job2 = client.post("/api/v1/jobs", headers=h, json={
        "code": "JOB-LONG-PREFIX-0002",
        "title": "Batch B Choker",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.0,
        "headKarigarId": k["id"],
        "dueDate": "2026-12-30",
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-COL-BAR",
        "source": "Audit Certified Bar",
        "grossWeightG": 100.000,
        "netWeightG": 100.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Issue 40.000 g (36.640 g fine) to each job
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job1["id"],
        "karigarId": k["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
    })
    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job2["id"],
        "karigarId": k["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
    })

    # Return only 35.000 g on Job 1 (variance = 5.000 g gross = 4.580 g fine > 0.366 g allowance)
    client.post("/api/v1/returns", headers=h, json={
        "jobId": job1["id"],
        "karigarId": k["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 35.000,
        "netMetalWeightG": 35.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # Return only 34.000 g on Job 2 (variance = 6.000 g gross = 5.496 g fine > 0.366 g allowance)
    client.post("/api/v1/returns", headers=h, json={
        "jobId": job2["id"],
        "karigarId": k["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 34.000,
        "netMetalWeightG": 34.000,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    # Reconcile both jobs
    client.post(f"/api/v1/jobs/{job1['id']}/reconcile", headers=h)
    client.post(f"/api/v1/jobs/{job2['id']}/reconcile", headers=h)

    # Detect exceptions for Job 1
    ex1 = client.post(f"/api/v1/exceptions/detect?jobId={job1['id']}", headers=h).json()
    assert len(ex1) >= 1
    case1 = ex1[0]
    assert case1["jobId"] == job1["id"]

    # Detect exceptions for Job 2
    ex2 = client.post(f"/api/v1/exceptions/detect?jobId={job2['id']}", headers=h).json()
    assert len(ex2) >= 1
    case2 = ex2[0]
    assert case2["jobId"] == job2["id"]

    # Codes must be distinct, sequential, and not collide
    assert case1["code"] != case2["code"]
    assert len(case1["code"]) <= 24
    assert len(case2["code"]) <= 24

    # Verify that detecting again on Job 1 does not create duplicate cases
    ex1_again = client.post(f"/api/v1/exceptions/detect?jobId={job1['id']}", headers=h).json()
    assert ex1_again == []

    # And verify both jobs keep their distinct cases intact via list endpoint
    cases_j1 = client.get(f"/api/v1/exceptions?jobId={job1['id']}", headers=h).json()
    cases_j2 = client.get(f"/api/v1/exceptions?jobId={job2['id']}", headers=h).json()

    j1_ids = {c["id"] for c in cases_j1["items"]}
    j2_ids = {c["id"] for c in cases_j2["items"]}
    ex1_ids = {c["id"] for c in ex1}
    ex2_ids = {c["id"] for c in ex2}

    assert j1_ids == ex1_ids
    assert j2_ids == ex2_ids
    assert j1_ids.isdisjoint(j2_ids)


def test_settlement_rule_selection_by_karat_and_effective_dates(client, admin):
    """Verifies that rule selection automatically picks the active rule matching job karat

    and effective date, ignoring expired, future, or wrong-karat rules.
    """
    h = admin["h"]
    k = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-RULE-SEL",
        "name": "Rule Selection Karigar",
        "kind": "head_karigar",
    }).json()

    # Rule A: 18K rule, effective 2026-01-01 to 2026-12-31 (wrong karat)
    rule_18k = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-18K-STD",
        "name": "18K Standard Rate",
        "karat": "18K",
        "labourRatePerG": 350.0,
        "lossAllowancePct": 1.0,
        "goldRatePerFineG": 7000.0,
        "effectiveFrom": "2026-01-01",
        "effectiveTo": "2026-12-31",
    }).json()

    # Rule B: 22K rule expired in H1 (effective 2026-01-01 to 2026-06-30)
    rule_22k_expired = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-22K-EXP",
        "name": "22K Expired Rate",
        "karat": "22K",
        "labourRatePerG": 400.0,
        "lossAllowancePct": 1.2,
        "goldRatePerFineG": 6800.0,
        "effectiveFrom": "2026-01-01",
        "effectiveTo": "2026-06-30",
    }).json()

    # Rule C: 22K rule active right now (effective 2026-07-01 to 2026-12-31), ₹420/g
    rule_22k_active = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-22K-ACT",
        "name": "22K Active Rate",
        "karat": "22K",
        "labourRatePerG": 420.0,
        "lossAllowancePct": 1.2,
        "goldRatePerFineG": 7200.0,
        "effectiveFrom": "2026-07-01",
        "effectiveTo": "2026-12-31",
    }).json()

    # Rule D: 22K rule in the future (effective 2026-12-15), ₹550/g
    rule_22k_future = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-22K-FUT",
        "name": "22K Future Holiday Rate",
        "karat": "22K",
        "labourRatePerG": 550.0,
        "lossAllowancePct": 1.5,
        "goldRatePerFineG": 7600.0,
        "effectiveFrom": "2026-12-15",
    }).json()

    # Job A: Karat 22K
    job_22k = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-SELECT-22K",
        "title": "22K Selection Test",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.2,
        "headKarigarId": k["id"],
        "dueDate": "2026-12-30",
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-SEL-BAR",
        "source": "Selection Bar",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job_22k["id"],
        "karigarId": k["id"],
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "measurement": MEAS,
    })

    client.post("/api/v1/returns", headers=h, json={
        "jobId": job_22k["id"],
        "karigarId": k["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 29.500,
        "netMetalWeightG": 29.500,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    client.post(f"/api/v1/jobs/{job_22k['id']}/reconcile", headers=h)

    # Generate worksheet WITHOUT specifying settlementRuleId
    sheet = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": job_22k["id"],
        "karigarId": k["id"],
    }).json()

    # Must select 22K active rule (SR-22K-ACT @ ₹420/g), NOT 18K rule (₹350/g), NOT expired rule, and NOT future rule (₹550/g)
    assert sheet["settlementRuleId"] == rule_22k_active["id"]
    assert sheet["labourRateApplied"] == 420.0
    assert sheet["goldRateApplied"] == 7200.0


def test_approval_controls_draft_self_and_unauthorized(client, admin, make_user):
    """Verifies:

    1. Draft cannot be approved directly (422 invalid_status).
    2. Creator cannot approve their own worksheet (403 self_approval_forbidden).
    3. Unauthorized role cannot approve (403 forbidden).
    4. Legitimate separate manager/admin can approve (200).
    """
    h_admin = admin["h"]
    manager_creator = make_user("manager", "creator_mgr@example.com")
    manager_approver = make_user("manager", "approver_mgr@example.com")
    vault_op = make_user("vault_operator", "vault_guard@example.com")

    k = client.post("/api/v1/karigars", headers=h_admin, json={
        "code": "K-APPR-TEST",
        "name": "Approval Test Karigar",
        "kind": "head_karigar",
    }).json()

    job = client.post("/api/v1/jobs", headers=h_admin, json={
        "code": "J-APPR-TEST",
        "title": "Approval Test Job",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.0,
        "headKarigarId": k["id"],
        "dueDate": "2026-12-30",
    }).json()

    lot = client.post("/api/v1/lots", headers=h_admin, json={
        "code": "L-APPR-TEST",
        "source": "Bar 916",
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h_admin, json={
        "jobId": job["id"],
        "karigarId": k["id"],
        "grossWeightG": 20.000,
        "netWeightG": 20.000,
        "measurement": MEAS,
    })

    client.post("/api/v1/returns", headers=h_admin, json={
        "jobId": job["id"],
        "karigarId": k["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 19.800,
        "netMetalWeightG": 19.800,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h_admin)

    # 1. Creator generates worksheet
    ws = client.post("/api/v1/settlements/worksheets", headers=manager_creator["h"], json={
        "jobId": job["id"],
        "karigarId": k["id"],
    }).json()
    assert ws["status"] == "draft"

    # 2. Cannot approve worksheet in 'draft' status directly
    r_draft = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/approve", headers=manager_approver["h"], json={})
    assert r_draft.status_code == 422
    assert r_draft.json()["error"]["code"] == "invalid_status"

    # 3. Submit worksheet
    r_sub = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/submit", headers=manager_creator["h"])
    assert r_sub.status_code == 200
    assert r_sub.json()["status"] == "submitted"

    # 4. Creator attempts self-approval -> must return 403 self_approval_forbidden
    r_self = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/approve", headers=manager_creator["h"], json={})
    assert r_self.status_code == 403
    assert r_self.json()["error"]["code"] == "self_approval_forbidden"

    # 5. Unauthorized role (vault operator) attempts to approve -> must return 403
    r_unauth = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/approve", headers=vault_op["h"], json={})
    assert r_unauth.status_code == 403

    # 6. Separate authorized manager approves -> succeeds with 200
    r_ok = client.post(f"/api/v1/settlements/worksheets/{ws['id']}/approve", headers=manager_approver["h"], json={
        "notes": "Approved under secondary manager review.",
    })
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "approved"

    # Job status transitioned to settled
    j_check = client.get(f"/api/v1/jobs/{job['id']}", headers=h_admin).json()
    assert j_check["status"] == "settled"


def test_monetary_values_quantized_to_paise(client, admin):
    """Verifies that labour amounts, gold recovery amounts, and net payable are rounded

    to ₹0.01 (paise precision) using Decimal half-up arithmetic.
    """
    h = admin["h"]
    k = client.post("/api/v1/karigars", headers=h, json={
        "code": "K-PAISE-01",
        "name": "Paise Precision Artisan",
        "kind": "head_karigar",
    }).json()

    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-PAISE-01",
        "title": "Paise Precision Job",
        "karat": "22K",
        "pieces": 1,
        "lossAllowancePct": 1.0,
        "headKarigarId": k["id"],
        "dueDate": "2026-12-30",
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-PAISE-01",
        "source": "Paise Bar",
        "grossWeightG": 30.000,
        "netWeightG": 30.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": k["id"],
        "grossWeightG": 20.000,
        "netWeightG": 20.000,
        "measurement": MEAS,
    })

    # Return 18.333 g finished jewellery
    client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": k["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 18.333,
        "netMetalWeightG": 18.333,
        "declaredFinenessPpt": 916.0,
        "pieces": 1,
        "isPartial": False,
        "measurement": MEAS,
    })

    client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h)

    # Rule with fractional labour rate per gram: ₹456.78
    rule = client.post("/api/v1/settlements/rules", headers=h, json={
        "code": "SR-PAISE-01",
        "name": "Paise Test Rule",
        "karat": "22K",
        "labourRatePerG": 456.78,
        "lossAllowancePct": 1.0,
        "goldRatePerFineG": 7123.45,
        "effectiveFrom": "2026-01-01",
    }).json()

    sheet = client.post("/api/v1/settlements/worksheets", headers=h, json={
        "jobId": job["id"],
        "karigarId": k["id"],
        "settlementRuleId": rule["id"],
        "approvedDeductions": 12.34,
    }).json()

    # 18.333 g * 456.78 = 8374.14774 -> 8374.15
    assert sheet["labourAmount"] == 8374.15
    # Total issued fine = 20.000 * 0.916 = 18.320 g
    # Finished fine = 18.333 * 0.916 = 16.793 g
    # Unexplained variance = 18.320 - 16.793 = 1.527 g
    # Wastage allowance = 18.320 * 1.0% = 0.183 g
    # Excess loss = 1.527 - 0.183 = 1.344 g fine
    # Recovery = 1.344 * 7123.45 = 9573.9168 -> 9573.92
    assert sheet["goldRecoveryAmount"] == 9573.92
    # Net payable = 8374.15 - 9573.92 - 12.34 = -1212.11
    assert sheet["netPayableAmount"] == -1212.11


def test_user_password_rotation_via_patch(client, admin):
    """Verifies that an admin can rotate a user's password via PATCH /api/v1/users/{id}

    and the user can subsequently log in with the new password while the old password fails.
    """
    h_admin = admin["h"]

    # 1. Create a user
    user = client.post("/api/v1/users", headers=h_admin, json={
        "email": "rotatetest@example.com",
        "fullName": "Rotate Target User",
        "role": "vault_operator",
        "password": "OldInitialPassword-2026!",
    }).json()

    # 2. Login with old password succeeds
    login_old = client.post("/api/v1/auth/login", json={
        "email": "rotatetest@example.com",
        "password": "OldInitialPassword-2026!",
    })
    assert login_old.status_code == 200

    # 3. Admin rotates password to new secure password
    patch_r = client.patch(f"/api/v1/users/{user['id']}", headers=h_admin, json={
        "password": "NewRotatedPassword-2026!#",
    })
    assert patch_r.status_code == 200

    # 4. Login with old password fails
    login_fail = client.post("/api/v1/auth/login", json={
        "email": "rotatetest@example.com",
        "password": "OldInitialPassword-2026!",
    })
    assert login_fail.status_code == 401
    assert login_fail.json()["error"]["code"] == "invalid_credentials"

    # 5. Login with new password succeeds
    login_new = client.post("/api/v1/auth/login", json={
        "email": "rotatetest@example.com",
        "password": "NewRotatedPassword-2026!#",
    })
    assert login_new.status_code == 200
    assert login_new.json()["user"]["email"] == "rotatetest@example.com"
