"""Tests for exception detection, resolution lifecycle, and AI investigation assistant."""

import pytest


MEAS = {"scaleId": "SC-EX-01", "operatorName": "QC Inspector", "method": "manual"}


@pytest.fixture()
def exception_world(client, admin):
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-EX-HEAD", "name": "Govind Karigar", "kind": "head_karigar"}).json()
    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-RING-SET",
        "title": "Diamond Cocktail Rings",
        "karat": "22K",
        "pieces": 5,
        "lossAllowancePct": 1.0,
        "headKarigarId": head["id"],
        "dueDate": "2026-11-01",  # Past due date to trigger overdue check
    }).json()
    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-RING-LOT",
        "source": "916 Grains",
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

    # Return with a severe purity shortfall (declared 916.0, assayed 890.0 ppt -> 26 ppt deficit)
    ret = client.post("/api/v1/returns", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "lotId": lot["id"],
        "returnCategory": "finished_jewellery",
        "grossWeightG": 20.000,
        "netMetalWeightG": 20.000,
        "declaredFinenessPpt": 916.0,
        "assayedFinenessPpt": 890.0,
        "measurement": MEAS,
    }).json()

    # Run reconciliation (which will show above allowance due to shortfall + missing 5g)
    client.post(f"/api/v1/jobs/{job['id']}/reconcile", headers=h)

    return {"h": h, "head": head, "job": job, "lot": lot, "ret": ret}


def test_exception_detection_and_lifecycle(client, exception_world, make_user):
    w = exception_world
    h = w["h"]
    investigator = make_user("manager", "investigator@example.com")

    # 1. Trigger automated exception scan
    detect_r = client.post(f"/api/v1/exceptions/detect?jobId={w['job']['id']}", headers=h)
    assert detect_r.status_code == 200
    detected = detect_r.json()
    assert len(detected) >= 1

    # Verify purity mismatch and/or variance exception exists
    purity_cases = [c for c in detected if c["exceptionType"] == "purity_mismatch"]
    assert len(purity_cases) >= 1
    case = purity_cases[0]
    assert case["status"] == "open"

    # 2. Assign investigator
    assign_r = client.patch(f"/api/v1/exceptions/{case['id']}/assign", headers=h, json={
        "investigatorId": investigator["user"]["id"]
    })
    assert assign_r.status_code == 200
    assert assign_r.json()["assignedInvestigatorId"] == investigator["user"]["id"]
    assert assign_r.json()["status"] == "investigating"

    # 3. Add investigation notes
    notes_r = client.post(f"/api/v1/exceptions/{case['id']}/notes", headers=h, json={
        "notes": "Verified fire assay counterfoil from refinery; purity confirmed 890 ppt."
    })
    assert notes_r.status_code == 200
    assert "Verified fire assay" in notes_r.json()["investigationNotes"]

    # 4. Attach evidence
    ev_r = client.post(f"/api/v1/exceptions/{case['id']}/evidence", headers=h, json={
        "evidenceType": "assay_certificate",
        "title": "Refinery Fire Assay Slip #9901",
        "fileUrl": "https://vault.example.com/slips/9901.pdf",
        "details": {"fineness": 890.0, "lab": "Govt Hallmarking Center"},
    })
    assert ev_r.status_code == 201

    # 5. Resolve exception
    res_r = client.post(f"/api/v1/exceptions/{case['id']}/resolve", headers=h, json={
        "resolutionNotes": "Recovery deduction applied to karigar settlement account."
    })
    assert res_r.status_code == 200
    resolved = res_r.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolutionNotes"] == "Recovery deduction applied to karigar settlement account."
    assert resolved["resolutionTimestamp"] is not None


def test_exception_dismissal_requires_reason(client, exception_world):
    w = exception_world
    h = w["h"]

    detect_r = client.post(f"/api/v1/exceptions/detect?jobId={w['job']['id']}", headers=h).json()
    case = detect_r[0]

    # Dismiss without valid reason must fail
    fail_r = client.post(f"/api/v1/exceptions/{case['id']}/dismiss", headers=h, json={"reason": ""})
    assert fail_r.status_code == 422

    # Dismiss with proper explanation succeeds
    ok_r = client.post(f"/api/v1/exceptions/{case['id']}/dismiss", headers=h, json={
        "reason": "Tolerance was agreed by manufacturing director under special contract addendum."
    })
    assert ok_r.status_code == 200
    assert ok_r.json()["status"] == "dismissed"


def test_ai_investigation_assistant_evidence_linking(client, exception_world):
    w = exception_world
    h = w["h"]

    detect_r = client.post(f"/api/v1/exceptions/detect?jobId={w['job']['id']}", headers=h).json()
    case = detect_r[0]

    # Run AI Investigation
    ai_r = client.post("/api/v1/investigations/run", headers=h, json={"exceptionId": case["id"]})
    assert ai_r.status_code == 201
    inv = ai_r.json()

    assert inv["exceptionId"] == case["id"]
    assert inv["jobId"] == w["job"]["id"]

    resp = inv["response"]
    assert "summary" in resp
    assert "verifiedFacts" in resp
    assert "suspectedCauses" in resp
    assert "evidence" in resp
    assert "calculationBreakdown" in resp
    assert "recommendedActions" in resp
    assert len(resp["verifiedFacts"]) >= 1
    assert len(resp["evidence"]) >= 1

    # Check evidence grounding: recordId matches real database entities
    evidence_ids = [e["recordId"] for e in resp["evidence"]]
    assert any(eid == w["job"]["id"] or eid == w["ret"]["id"] for eid in evidence_ids)


def test_ai_tools_read_only_access(client, exception_world):
    w = exception_world
    h = w["h"]

    # Test executing read-only tools
    job_summary = client.get(f"/api/v1/investigations/tools/get_job_summary?jobId={w['job']['id']}", headers=h).json()
    assert job_summary["code"] == "J-RING-SET"

    ledger = client.get(f"/api/v1/investigations/tools/get_job_ledger?jobId={w['job']['id']}", headers=h).json()
    assert len(ledger) >= 2  # Issue and Return

    lot_trace = client.get(f"/api/v1/investigations/tools/trace_material_lot?lotId={w['lot']['id']}", headers=h).json()
    assert lot_trace["code"] == "L-RING-LOT"

    bal = client.get(f"/api/v1/investigations/tools/calculate_fine_gold_balance?jobId={w['job']['id']}", headers=h).json()
    assert "issuedFineG" in bal


def test_ai_provider_gemini_fallback(client, exception_world, monkeypatch):
    """Verify that when Gemini provider is configured with an invalid/mocked key, it safely falls back to deterministic provider."""
    w = exception_world
    h = w["h"]

    detect_r = client.post(f"/api/v1/exceptions/detect?jobId={w['job']['id']}", headers=h).json()
    case = detect_r[0]

    # Configure Gemini with a dummy key and simulate network failure
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic-invalid-gemini-key")

    ai_r = client.post("/api/v1/investigations/run", headers=h, json={"exceptionId": case["id"]})
    assert ai_r.status_code == 201
    inv = ai_r.json()

    # Provider should indicate fallback
    assert "gemini_fallback" in inv["provider"]
    assert inv["response"]["summary"]
    assert len(inv["response"]["verifiedFacts"]) >= 1
