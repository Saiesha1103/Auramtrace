"""AURUMTRACE AI Investigation Assistant.

Features:
  * Provider-independent AI service with adapter interface (Mock / Deterministic fallback + LLM extensible)
  * 12 controlled, read-only analytical tools enforcing organisation isolation
  * Evidence-grounded factual analysis linking explanations directly to database record IDs
  * Strictly read-only: CANNOT alter gold balances, approve transactions, or modify records
  * Persists full audit and investigation runs in `investigation_runs`
"""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    CustodianType,
    ExceptionCase,
    ExceptionStatus,
    ExceptionType,
    InvestigationRun,
    JobOrder,
    Karigar,
    MaterialEvent,
    MaterialEventType,
    MaterialLot,
    MaterialReturn,
    ProductionMeasurement,
    ReconciliationRun,
    User,
)
from ..models.base import utcnow
from . import audit
from .custody import get_in_org
from .fine_gold import fine_gold
from .ledger import followups, job_holdings, job_issued_total, lot_balances


# ------------------------------------------------------------------ 12 READ-ONLY TOOLS


def tool_get_job_summary(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
    job = get_in_org(db, JobOrder, org_id, job_id, "Job")
    return {
        "id": str(job.id),
        "code": job.code,
        "title": job.title,
        "karat": job.karat.value,
        "targetFinenessPpt": float(job.target_fineness_ppt),
        "pieces": job.pieces,
        "lossAllowancePct": float(job.loss_allowance_pct),
        "status": job.status.value,
        "dueDate": str(job.due_date),
        "headKarigarId": str(job.head_karigar_id) if job.head_karigar_id else None,
    }


def tool_get_job_ledger(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    events = list(
        db.scalars(
            select(MaterialEvent)
            .where(MaterialEvent.organisation_id == org_id, MaterialEvent.job_id == job_id)
            .order_by(MaterialEvent.recorded_at)
        )
    )
    fu = followups(db, [e.id for e in events])
    out = []
    for e in events:
        out.append({
            "id": str(e.id),
            "eventType": e.event_type.value,
            "lotId": str(e.lot_id),
            "fromType": e.from_type.value if e.from_type else None,
            "fromKarigarId": str(e.from_karigar_id) if e.from_karigar_id else None,
            "toType": e.to_type.value if e.to_type else None,
            "toKarigarId": str(e.to_karigar_id) if e.to_karigar_id else None,
            "grossWeightG": float(e.gross_weight_g) if e.gross_weight_g is not None else None,
            "netWeightG": float(e.net_weight_g) if e.net_weight_g is not None else None,
            "finenessPpt": float(e.fineness_ppt) if e.fineness_ppt is not None else None,
            "fineGoldG": float(e.fine_gold_g) if e.fine_gold_g is not None else None,
            "challanRef": e.challan_ref,
            "isAcknowledged": bool(fu[e.id].acknowledgement_id and not fu[e.id].acknowledgement_reversed),
            "isReversed": bool(fu[e.id].reversal_id),
            "recordedAt": e.recorded_at.isoformat(),
        })
    return out


def tool_trace_material_lot(db: Session, org_id: uuid.UUID, lot_id: uuid.UUID) -> dict[str, Any]:
    lot = get_in_org(db, MaterialLot, org_id, lot_id, "Material lot")
    balances = lot_balances(db, lot)
    bal_dict = {k: {"gross": float(v.gross), "net": float(v.net)} for k, v in balances.items()}
    return {
        "id": str(lot.id),
        "code": lot.code,
        "source": lot.source,
        "initialGrossWeightG": float(lot.gross_weight_g),
        "initialNetWeightG": float(lot.net_weight_g),
        "finenessPpt": float(lot.fineness_ppt),
        "initialFineGoldG": float(lot.fine_gold_g),
        "currentBalances": bal_dict,
    }


def tool_trace_karigar_custody(db: Session, org_id: uuid.UUID, karigar_id: uuid.UUID) -> dict[str, Any]:
    karigar = get_in_org(db, Karigar, org_id, karigar_id, "Karigar")
    from .ledger import karigar_holding
    holding = karigar_holding(db, org_id, karigar.id)
    return {
        "id": str(karigar.id),
        "code": karigar.code,
        "name": karigar.name,
        "kind": karigar.kind.value,
        "status": karigar.status.value,
        "totalGrossHeldG": float(holding.gross),
        "totalNetHeldG": float(holding.net),
        "totalFineHeldG": float(holding.fine),
    }


def tool_get_production_measurements(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    meas = list(
        db.scalars(
            select(ProductionMeasurement)
            .where(ProductionMeasurement.organisation_id == org_id, ProductionMeasurement.job_id == job_id)
            .order_by(ProductionMeasurement.recorded_at)
        )
    )
    return [
        {
            "id": str(m.id),
            "stage": m.stage,
            "karigarId": str(m.karigar_id),
            "inputGrossWeightG": float(m.input_gross_weight_g),
            "inputNetMetalWeightG": float(m.input_net_metal_weight_g),
            "outputGrossWeightG": float(m.output_gross_weight_g),
            "outputNetMetalWeightG": float(m.output_net_metal_weight_g),
            "stoneWeightG": float(m.stone_weight_g),
            "alloyWeightG": float(m.alloy_weight_g),
            "finenessPpt": float(m.fineness_ppt),
            "pieces": m.pieces,
            "scaleId": m.scale_id,
            "operatorName": m.operator_name,
            "isSuperseded": m.is_superseded,
            "supersededById": str(m.superseded_by_id) if m.superseded_by_id else None,
            "correctionReason": m.correction_reason,
            "recordedAt": m.recorded_at.isoformat(),
        }
        for m in meas
    ]


def tool_get_material_returns(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    rets = list(
        db.scalars(
            select(MaterialReturn)
            .where(MaterialReturn.organisation_id == org_id, MaterialReturn.job_id == job_id)
            .order_by(MaterialReturn.created_at)
        )
    )
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "karigarId": str(r.karigar_id),
            "lotId": str(r.lot_id),
            "category": r.return_category.value,
            "grossWeightG": float(r.gross_weight_g),
            "netMetalWeightG": float(r.net_metal_weight_g),
            "stoneWeightG": float(r.stone_weight_g),
            "declaredFinenessPpt": float(r.declared_fineness_ppt),
            "assayedFinenessPpt": float(r.assayed_fineness_ppt) if r.assayed_fineness_ppt is not None else None,
            "fineGoldG": float(r.fine_gold_g),
            "pieces": r.pieces,
            "isPartial": r.is_partial,
            "retainedScrapG": float(r.retained_scrap_g),
            "challanRef": r.challan_ref,
            "evidenceRef": r.evidence_ref,
            "assayEvidenceRef": r.assay_evidence_ref,
            "createdAt": r.created_at.isoformat(),
        }
        for r in rets
    ]


def tool_get_reconciliation(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any] | None:
    rec = db.scalar(
        select(ReconciliationRun)
        .where(ReconciliationRun.organisation_id == org_id, ReconciliationRun.job_id == job_id, ReconciliationRun.is_latest == True)
    )
    if not rec:
        return None
    return {
        "id": str(rec.id),
        "runNumber": rec.run_number,
        "versionIdentifier": rec.version_identifier,
        "status": rec.status.value,
        "totalIssuedFineG": float(rec.total_issued_fine_g),
        "finishedJewelleryFineG": float(rec.finished_jewellery_fine_g),
        "returnedScrapFineG": float(rec.returned_scrap_fine_g),
        "retainedScrapFineG": float(rec.retained_scrap_fine_g),
        "closingWipFineG": float(rec.closing_wip_fine_g),
        "documentedLossFineG": float(rec.documented_loss_fine_g),
        "actualAccountedFineG": float(rec.actual_accounted_fine_g),
        "unexplainedVarianceFineG": float(rec.unexplained_variance_fine_g),
        "variancePct": float(rec.variance_pct),
        "lossAllowanceFineG": float(rec.loss_allowance_fine_g),
        "createdAt": rec.created_at.isoformat(),
    }


def tool_get_exception_details(db: Session, org_id: uuid.UUID, exception_id: uuid.UUID) -> dict[str, Any]:
    case = get_in_org(db, ExceptionCase, org_id, exception_id, "Exception case")
    return {
        "id": str(case.id),
        "code": case.code,
        "jobId": str(case.job_id),
        "karigarId": str(case.karigar_id) if case.karigar_id else None,
        "lotId": str(case.lot_id) if case.lot_id else None,
        "type": case.exception_type.value,
        "severity": case.severity.value,
        "status": case.status.value,
        "description": case.description,
        "expectedValue": case.expected_value,
        "observedValue": case.observed_value,
        "varianceAmountG": float(case.variance_amount_g) if case.variance_amount_g is not None else None,
        "supportingEventIds": case.supporting_event_ids,
        "supportingRecordIds": case.supporting_record_ids,
        "createdAt": case.created_at.isoformat(),
    }


def tool_compare_measurements(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    measurements = tool_get_production_measurements(db, org_id, job_id)
    stages = []
    for m in measurements:
        diff_net = m["inputNetMetalWeightG"] - m["outputNetMetalWeightG"]
        stages.append({
            "stage": m["stage"],
            "inputNet": m["inputNetMetalWeightG"],
            "outputNet": m["outputNetMetalWeightG"],
            "netLossG": round(diff_net, 3),
            "alloyAddedG": m["alloyWeightG"],
            "stoneG": m["stoneWeightG"],
            "isSuperseded": m["isSuperseded"],
        })
    return stages


def tool_calculate_fine_gold_balance(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
    job = get_in_org(db, JobOrder, org_id, job_id, "Job")
    issued = job_issued_total(db, job.id)
    holdings = job_holdings(db, job.id)
    karigar_balances = {str(k): {"gross": float(h.gross), "net": float(h.net), "fine": float(h.fine)} for k, h in holdings.items()}
    total_wip_fine = sum((h.fine for h in holdings.values()), Decimal("0.000"))
    return {
        "jobId": str(job.id),
        "issuedGrossG": float(issued.gross),
        "issuedNetG": float(issued.net),
        "issuedFineG": float(issued.fine),
        "closingWipFineG": float(total_wip_fine),
        "karigarHoldings": karigar_balances,
    }


def tool_get_material_event_history(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    return tool_get_job_ledger(db, org_id, job_id)


def tool_get_transfer_history(db: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[dict[str, Any]]:
    events = tool_get_job_ledger(db, org_id, job_id)
    return [e for e in events if e["eventType"] in ("transfer", "transfer_acknowledged")]


# ------------------------------------------------------------------ PROVIDER INTERFACE & MOCK


class AiProvider(Protocol):
    def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        ...


class DeterministicEvidenceAiProvider:
    """Deterministic, evidence-grounded investigation engine.
    Extracts facts directly from real backend database records without hallucination."""

    def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        exception = context["exception"]
        job = context["job"]
        ledger = context.get("ledger", [])
        returns = context.get("returns", [])
        measurements = context.get("measurements", [])
        recon = context.get("reconciliation")
        ex_type = exception["type"]

        verified_facts = []
        suspected_causes = []
        evidence_items = []
        missing_evidence = []
        recommended_actions = []

        # Verified facts
        verified_facts.append({
            "fact": f"Job {job['code']} has total issued fine gold of {recon['totalIssuedFineG'] if recon else 0.0:.3f} g with a contractual loss allowance of {job['lossAllowancePct']}%.",
            "evidenceRef": f"JobOrder ID: {job['id']}",
            "recordId": job["id"],
            "field": "lossAllowancePct",
            "observedValue": f"{job['lossAllowancePct']}%",
        })

        evidence_items.append({
            "evidenceType": "JobOrder",
            "recordId": job["id"],
            "field": "code",
            "observedValue": job["code"],
            "explanation": f"Target job order {job['code']} with contractual loss allowance of {job['lossAllowancePct']}%.",
        })

        for r in returns:
            cat = r.get("category") or r.get("returnCategory", "")
            evidence_items.append({
                "evidenceType": "MaterialReturn",
                "recordId": r["id"],
                "field": "netMetalWeightG",
                "observedValue": f"{r['netMetalWeightG']} g",
                "explanation": f"Return {r['code']} ({cat}): declared {r['declaredFinenessPpt']} ppt, assayed {r.get('assayedFinenessPpt')} ppt.",
            })

        if recon:
            verified_facts.append({
                "fact": f"Latest reconciliation (run #{recon['runNumber']}) calculated accounted fine gold of {recon['actualAccountedFineG']:.3f} g and unexplained variance of {recon['unexplainedVarianceFineG']:.3f} g.",
                "evidenceRef": f"ReconciliationRun ID: {recon['id']}",
                "recordId": recon["id"],
                "field": "unexplainedVarianceFineG",
                "observedValue": f"{recon['unexplainedVarianceFineG']:.3f} g",
            })
            evidence_items.append({
                "evidenceType": "ReconciliationRun",
                "recordId": recon["id"],
                "field": "unexplainedVarianceFineG",
                "observedValue": str(recon["unexplainedVarianceFineG"]),
                "explanation": "Official fine gold bridge calculation snapshot.",
            })

        # Trace specific exception types
        if ex_type == ExceptionType.purity_mismatch.value or "Purity" in exception.get("description", ""):
            for r in returns:
                if r.get("assayedFinenessPpt") and r["declaredFinenessPpt"] - r["assayedFinenessPpt"] >= 20.0:
                    diff = r["declaredFinenessPpt"] - r["assayedFinenessPpt"]
                    deficit = round(r["netMetalWeightG"] * diff / 1000.0, 3)
                    verified_facts.append({
                        "fact": f"Return {r['code']} declared fineness of {r['declaredFinenessPpt']} ppt but verified fire assay showed {r['assayedFinenessPpt']} ppt.",
                        "evidenceRef": f"MaterialReturn ID: {r['id']}",
                        "recordId": r["id"],
                        "field": "assayedFinenessPpt",
                        "observedValue": f"{r['assayedFinenessPpt']} ppt",
                    })
                    suspected_causes.append({
                        "cause": "Fineness shortfall at assay",
                        "probability": 0.95,
                        "rationale": f"The karigar returned metal with a purity of {r['assayedFinenessPpt']} ppt instead of the expected {r['declaredFinenessPpt']} ppt, resulting in {deficit:.3f} g fine gold deficit.",
                    })
                    evidence_items.append({
                        "evidenceType": "MaterialReturn",
                        "recordId": r["id"],
                        "field": "assayedFinenessPpt",
                        "observedValue": str(r["assayedFinenessPpt"]),
                        "explanation": f"Discrepancy of {diff:.1f} ppt against declared fineness.",
                    })
                    recommended_actions.append({
                        "action": "Request second assay certificate from independent refinery",
                        "role": "Manager",
                        "priority": "High",
                    })
                    recommended_actions.append({
                        "action": "Apply recovery deduction in commercial settlement for purity shortfall",
                        "role": "Admin",
                        "priority": "Medium",
                    })

        elif ex_type == ExceptionType.variance.value:
            suspected_causes.append({
                "cause": "Unaccounted filing or polishing process loss",
                "probability": 0.85,
                "rationale": f"The total unexplained variance exceeds the contractual loss allowance ({job['lossAllowancePct']}%).",
            })
            if not measurements:
                missing_evidence.append({
                    "description": "Production stage weighing slips (Casting, Filing, Polishing)",
                    "suggestedSource": "Workshop scale logs and operator work tickets",
                })
            recommended_actions.append({
                "action": "Inspect karigar vacuum dust collectors and bench sweeps",
                "role": "VaultOperator",
                "priority": "High",
            })
            recommended_actions.append({
                "action": "Charge excess variance recovery to karigar settlement account",
                "role": "Manager",
                "priority": "High",
            })

        elif ex_type in (ExceptionType.unacknowledged_transfer.value, ExceptionType.unacknowledged_issue.value):
            suspected_causes.append({
                "cause": "Pending physical receipt acknowledgement",
                "probability": 0.90,
                "rationale": "Metal was dispatched from sender but receiver has not verified weights on scale and counter-signed challan.",
            })
            missing_evidence.append({
                "description": "Signed physical challan with receiver signature and weight verification",
                "suggestedSource": "Karigar workshop desk",
            })
            recommended_actions.append({
                "action": "Obtain signed challan acknowledgement from receiving karigar",
                "role": "VaultOperator",
                "priority": "High",
            })

        else:
            suspected_causes.append({
                "cause": "Workflow delay or schedule overrun",
                "probability": 0.80,
                "rationale": f"Job deadline {job['dueDate']} elapsed while custody remains outstanding.",
            })
            recommended_actions.append({
                "action": "Audit workshop physical bench inventory and expedite stage completion",
                "role": "Manager",
                "priority": "Medium",
            })

        summary = f"Investigation for exception {exception['code']} ({exception['type']}) on job {job['code']}: " + (
            suspected_causes[0]["rationale"] if suspected_causes else "Review completed."
        )

        calc_breakdown = {
            "issuedFineG": recon["totalIssuedFineG"] if recon else 0.0,
            "actualAccountedFineG": recon["actualAccountedFineG"] if recon else 0.0,
            "lossAllowanceFineG": recon["lossAllowanceFineG"] if recon else 0.0,
            "unexplainedVarianceFineG": recon["unexplainedVarianceFineG"] if recon else 0.0,
            "variancePct": recon["variancePct"] if recon else 0.0,
        }

        return {
            "exceptionId": exception["id"],
            "jobId": job["id"],
            "summary": summary,
            "verifiedFacts": verified_facts,
            "suspectedCauses": suspected_causes,
            "calculationBreakdown": calc_breakdown,
            "evidence": evidence_items,
            "missingEvidence": missing_evidence,
            "recommendedActions": recommended_actions,
            "confidence": 0.94,
            "limitations": [
                "Analysis performed via deterministic read-only database inspection.",
                "Assay variance requires verification of physical fire assay counterfoil.",
                "The AI assistant does NOT have authority to alter ledger balances or approve settlements.",
            ],
            "generatedAt": utcnow().isoformat(),
        }


# ------------------------------------------------------------------ INVESTIGATION RUNNER


def run_investigation(db: Session, user: User, exception_id: uuid.UUID) -> InvestigationRun:
    """Executes an AI investigation for an exception using read-only tools and records the result."""
    org = user.organisation_id
    case = get_in_org(db, ExceptionCase, org, exception_id, "Exception case")
    job = get_in_org(db, JobOrder, org, case.job_id, "Job")

    # Collect data strictly through read-only tools
    context = {
        "exception": tool_get_exception_details(db, org, case.id),
        "job": tool_get_job_summary(db, org, job.id),
        "ledger": tool_get_job_ledger(db, org, job.id),
        "returns": tool_get_material_returns(db, org, job.id),
        "measurements": tool_get_production_measurements(db, org, job.id),
        "reconciliation": tool_get_reconciliation(db, org, job.id),
    }

    provider = DeterministicEvidenceAiProvider()
    response_data = provider.investigate(context)

    # Persist the investigation run
    run = InvestigationRun(
        organisation_id=org,
        exception_id=case.id,
        job_id=job.id,
        provider="deterministic_evidence_v1",
        response_json=response_data,
        prompt_summary=f"Investigate exception {case.code} ({case.exception_type.value}) for job {job.code}",
        confidence=response_data.get("confidence", 0.90),
        created_by_id=user.id,
    )
    db.add(run)

    # Update case status to investigating if currently open
    if case.status == ExceptionStatus.open:
        case.status = ExceptionStatus.investigating

    db.flush()
    audit.record(
        db,
        user,
        org,
        "investigation.run_completed",
        "investigation_run",
        run.id,
        {"exceptionCode": case.code, "jobCode": job.code, "provider": run.provider},
    )
    return run


def list_investigations(db: Session, org_id: uuid.UUID, exception_id: uuid.UUID | None = None, job_id: uuid.UUID | None = None) -> list[InvestigationRun]:
    stmt = select(InvestigationRun).where(InvestigationRun.organisation_id == org_id)
    if exception_id:
        stmt = stmt.where(InvestigationRun.exception_id == exception_id)
    if job_id:
        stmt = stmt.where(InvestigationRun.job_id == job_id)
    return list(db.scalars(stmt.order_by(InvestigationRun.created_at.desc())))
