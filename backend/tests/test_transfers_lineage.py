"""Tests for material transfers, multi-level subcontracting, acknowledgements, reversals, and job lineage."""

import uuid
from decimal import Decimal

import pytest

from app.models import KarigarKind, MaterialEventType


MEAS = {"scaleId": "SC-02", "operatorName": "Bench supervisor", "method": "manual"}


@pytest.fixture()
def transfer_world(client, admin):
    """Sets up Head Karigar (K-01), Team Karigar (K-02), Subcontractor (K-03), Job, and 50.000 g 22K lot."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-HEAD", "name": "Head Master Ramesh", "kind": "head_karigar", "unit": "Unit 1"}).json()
    karigar = client.post("/api/v1/karigars", headers=h, json={"code": "K-ARTISAN", "name": "Artisan Suresh", "kind": "karigar", "headKarigarId": head["id"]}).json()
    subcontractor = client.post("/api/v1/karigars", headers=h, json={"code": "K-SUB", "name": "Setter Mukesh", "kind": "subcontractor", "headKarigarId": head["id"]}).json()

    job = client.post("/api/v1/jobs", headers=h, json={
        "code": "J-ROYAL",
        "title": "Royal Necklace Set",
        "karat": "22K",
        "pieces": 10,
        "lossAllowancePct": 1.5,
        "headKarigarId": head["id"],
        "dueDate": "2026-12-01",
    }).json()

    lot = client.post("/api/v1/lots", headers=h, json={
        "code": "L-GOLD-50",
        "source": "Bar 916 · Ref-99",
        "grossWeightG": 50.000,
        "netWeightG": 50.000,
        "finenessPpt": 916.0,
        "measurement": MEAS,
    }).json()

    # Issue 40.000 g from vault to Head Karigar
    issue_resp = client.post(f"/api/v1/lots/{lot['id']}/issue", headers=h, json={
        "jobId": job["id"],
        "karigarId": head["id"],
        "grossWeightG": 40.000,
        "netWeightG": 40.000,
        "measurement": MEAS,
        "challanRef": "ISSUE-01",
    })
    assert issue_resp.status_code == 201
    issue_ev = issue_resp.json()

    # Head karigar acknowledges issue
    client.post(f"/api/v1/events/{issue_ev['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Ramesh", "evidenceRef": "SIG-01"})

    return {
        "h": h,
        "head": head,
        "karigar": karigar,
        "subcontractor": subcontractor,
        "job": job,
        "lot": lot,
        "issue_ev": issue_ev,
    }


def test_transfer_creation_and_balance_deduction(client, transfer_world):
    w = transfer_world
    h = w["h"]

    # Transfer 15.000 g from Head Karigar to Team Karigar
    r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["karigar"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 15.000,
        "netWeightG": 15.000,
        "measurement": MEAS,
        "challanRef": "CH-TR-01",
        "note": "For preliminary wire drawing",
    })
    assert r.status_code == 201, r.text
    tr = r.json()
    assert tr["grossWeightG"] == 15.0
    assert tr["netWeightG"] == 15.0
    assert tr["finenessPpt"] == 916.0
    # Fine gold: 15.000 * 916.0 / 1000 = 13.740
    assert tr["fineGoldG"] == 13.74
    assert tr["fromKarigar"]["code"] == "K-HEAD"
    assert tr["toKarigar"]["code"] == "K-ARTISAN"
    assert not tr["isAcknowledged"]
    assert not tr["isReversed"]

    # Verify head karigar now has 40.000 - 15.000 = 25.000 g
    head_profile = client.get(f"/api/v1/karigars/{w['head']['id']}", headers=h).json()
    assert head_profile["custody"]["netWeightG"] == 25.0

    # Verify team karigar now has 15.000 g
    kar_profile = client.get(f"/api/v1/karigars/{w['karigar']['id']}", headers=h).json()
    assert kar_profile["custody"]["netWeightG"] == 15.0


def test_transfer_insufficient_balance_rejected(client, transfer_world):
    w = transfer_world
    h = w["h"]

    # Head karigar holds 40.000 g. Attempting to transfer 40.001 g must fail.
    r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["karigar"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 40.001,
        "netWeightG": 40.001,
        "measurement": MEAS,
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "insufficient_balance"


def test_self_transfer_rejected(client, transfer_world):
    w = transfer_world
    h = w["h"]

    r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["head"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 5.000,
        "netWeightG": 5.000,
        "measurement": MEAS,
    })
    assert r.status_code == 422


def test_transfer_acknowledgement_and_reversal_workflow(client, transfer_world):
    w = transfer_world
    h = w["h"]

    # 1. Create transfer: Head -> Karigar (10.000 g)
    r = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["karigar"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 10.000,
        "netWeightG": 10.000,
        "measurement": MEAS,
    })
    tr = r.json()

    # 2. Acknowledge transfer
    ack_r = client.post(f"/api/v1/transfers/{tr['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Suresh Artisan",
        "evidenceRef": "SIGN-SUR-01",
        "note": "Weighed on digital scale SC-02",
    })
    assert ack_r.status_code == 200
    ack_data = ack_r.json()
    assert ack_data["isAcknowledged"] is True
    assert ack_data["acknowledgedByName"] == "Suresh Artisan"

    # Cannot acknowledge twice
    ack_dup = client.post(f"/api/v1/transfers/{tr['id']}/acknowledge", headers=h, json={
        "acknowledgedByName": "Suresh",
    })
    assert ack_dup.status_code == 409

    # 3. Reverse transfer: should return 10.000 g back to Head
    rev_r = client.post(f"/api/v1/transfers/{tr['id']}/reverse", headers=h, json={
        "reason": "Transfer mistakenly booked under wrong artisan",
    })
    assert rev_r.status_code == 200
    rev_data = rev_r.json()
    assert rev_data["isReversed"] is True

    # Balances restored: Head = 40.000 g, Karigar = 0.000 g
    head_p = client.get(f"/api/v1/karigars/{w['head']['id']}", headers=h).json()
    kar_p = client.get(f"/api/v1/karigars/{w['karigar']['id']}", headers=h).json()
    assert head_p["custody"]["netWeightG"] == 40.0
    assert kar_p["custody"]["netWeightG"] == 0.0


def test_multi_level_subcontracting_chain(client, transfer_world):
    """Vault -> Head (40g) -> Karigar (20g) -> Subcontractor (8g)."""
    w = transfer_world
    h = w["h"]

    # Step 1: Head -> Karigar (20g)
    t1 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["karigar"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 20.000,
        "netWeightG": 20.000,
        "measurement": MEAS,
    }).json()
    client.post(f"/api/v1/transfers/{t1['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Suresh"})

    # Step 2: Karigar -> Subcontractor (8g)
    t2 = client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["karigar"]["id"],
        "toKarigarId": w["subcontractor"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 8.000,
        "netWeightG": 8.000,
        "measurement": MEAS,
        "note": "Stone setting sub-contract",
    }).json()
    client.post(f"/api/v1/transfers/{t2['id']}/acknowledge", headers=h, json={"acknowledgedByName": "Mukesh Setter"})

    # Check holdings across the chain
    # Head: 40 - 20 = 20g
    # Karigar: 20 - 8 = 12g
    # Subcontractor: 8g
    head_p = client.get(f"/api/v1/karigars/{w['head']['id']}", headers=h).json()
    kar_p = client.get(f"/api/v1/karigars/{w['karigar']['id']}", headers=h).json()
    sub_p = client.get(f"/api/v1/karigars/{w['subcontractor']['id']}", headers=h).json()

    assert head_p["custody"]["netWeightG"] == 20.0
    assert kar_p["custody"]["netWeightG"] == 12.0
    assert sub_p["custody"]["netWeightG"] == 8.0

    # Total custody across all 3 remains exactly 40.000 g
    assert head_p["custody"]["netWeightG"] + kar_p["custody"]["netWeightG"] + sub_p["custody"]["netWeightG"] == 40.0


def test_job_splitting_and_lineage(client, transfer_world):
    w = transfer_world
    h = w["h"]

    # Parent job has 10 pieces. Split 4 pieces into child job.
    split_r = client.post(f"/api/v1/jobs/{w['job']['id']}/split", headers=h, json={
        "allocatedPieces": 4,
        "allocatedGrossWeightG": 16.000,
        "splitReason": "Dedicated sub-contract for pendant section",
        "childTitle": "Royal Pendant Special Edition",
    })
    assert split_r.status_code == 201
    child = split_r.json()
    assert child["pieces"] == 4
    assert child["title"] == "Royal Pendant Special Edition"

    # Parent job pieces reduced from 10 to 6
    parent = client.get(f"/api/v1/jobs/{w['job']['id']}", headers=h).json()
    assert parent["pieces"] == 6

    # Verify lineage endpoint
    lineage = client.get(f"/api/v1/jobs/{w['job']['id']}/lineage", headers=h).json()
    assert lineage["jobId"] == w["job"]["id"]
    assert len(lineage["childJobs"]) == 1
    assert lineage["childJobs"][0]["id"] == child["id"]
    assert len(lineage["splits"]) == 1
    assert lineage["splits"][0]["allocatedPieces"] == 4


def test_custody_lineage_graph(client, transfer_world):
    w = transfer_world
    h = w["h"]

    # Execute transfer
    client.post("/api/v1/transfers", headers=h, json={
        "jobId": w["job"]["id"],
        "fromKarigarId": w["head"]["id"],
        "toKarigarId": w["karigar"]["id"],
        "lotId": w["lot"]["id"],
        "grossWeightG": 10.000,
        "netWeightG": 10.000,
        "measurement": MEAS,
    })

    graph = client.get(f"/api/v1/jobs/{w['job']['id']}/custody-lineage", headers=h).json()
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) >= 2
    assert len(graph["edges"]) >= 2  # Issue edge + Transfer edge
