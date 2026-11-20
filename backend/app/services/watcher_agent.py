"""Deadline & payment watcher agent.

Replaces "deadlines are chased by phone" and "artisans wait weeks to be paid": the agent looks at
open jobs against due dates and the customer's occasion date, and at approved-but-unpaid
settlements, then proposes prioritised alerts and DRAFT messages.

It never sends anything. Drafts are for a person to review, edit and send.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AgentRun, User
from . import audit
from .agent_runtime import AgentResult, GeminiPlanner, Planner, RulePlanner, Tool, ToolParam, run_agent
from .ai_investigation import tool_get_job_summary
from .track_record import jobs_at_risk, payment_delays, track_record

logger = logging.getLogger("aurumtrace.agent.watcher")

WATCHER_TOOLS: list[Tool] = [
    Tool(
        "list_jobs_at_risk",
        "Open jobs whose due date or customer occasion date (wedding, festival) is past or within horizon_days, with who holds the gold now.",
        (ToolParam("horizon_days", "integer", "Look-ahead window in days, e.g. 7"),),
        lambda db, org, horizon_days: jobs_at_risk(db, org, horizon_days),
    ),
    Tool(
        "list_payment_delays",
        "Settlements approved by the jeweller where the karigar has not been paid yet (awaiting acceptance, accepted, or disputed), longest wait first.",
        (ToolParam("min_days", "integer", "Only include waits of at least this many days", required=False),),
        lambda db, org, min_days=0: payment_delays(db, org, min_days),
    ),
    Tool(
        "get_karigar_track_record",
        "A karigar's delivery record: on-time rate, wastage within allowance, disputes, average days to payment.",
        (ToolParam("karigar_id", "uuid", "UUID of the karigar"),),
        lambda db, org, karigar_id: track_record(db, org, karigar_id),
    ),
    Tool(
        "get_job_summary",
        "Job order spec: karat, pieces, loss allowance, due date, head karigar.",
        (ToolParam("job_id", "uuid", "UUID of the job order"),),
        lambda db, org, job_id: tool_get_job_summary(db, org, job_id),
    ),
]

WATCHER_SYSTEM = (
    "You are the AURUMTRACE operations agent for a jeweller who gives gold to karigars (artisan goldsmiths) for job work. "
    "Your job each morning: find custom orders at risk of missing their due date or the customer's occasion date, and "
    "karigars who are waiting to be paid. Use the tools: start with list_jobs_at_risk and list_payment_delays, then look "
    "up track records or job details where that changes your advice.\n"
    "Prioritise: an occasion date (wedding) within 3 days is critical; a karigar waiting more than 7 days for payment is high. "
    "Be fair to the karigar: payment delays are the jeweller's responsibility, not the karigar's.\n"
    "You are READ-ONLY. You never send messages; you write drafts a person will review.\n"
    "When done, reply with ONLY a JSON object: {summary: str, alerts: [{kind: 'deadline'|'payment'|'dispute', severity: "
    "'critical'|'high'|'medium', title: str, detail: str, recordId: str (job or worksheet id from the tools), karigarId: str|null}], "
    "draftMessages: [{audience: 'karigar'|'jeweller'|'customer', karigarId: str|null, recordId: str, channel: 'whatsapp', text: str}], "
    "limitations: [str]}. Keep each draft under 400 characters, polite, and specific (job code, dates, grams, amounts)."
)

GOAL = "Run today's deadline and payment check for this workshop and propose alerts and draft messages. Horizon: {h} days."


# ------------------------------------------------------------------ deterministic planner


def _rule_planner(horizon: int) -> RulePlanner:
    def decide(seen: dict[str, Any]) -> list[tuple[str, dict[str, Any]]] | None:
        if "list_jobs_at_risk" not in seen:
            return [("list_jobs_at_risk", {"horizon_days": horizon}), ("list_payment_delays", {"min_days": 0})]
        # look closer at every karigar involved in a critical item (once each)
        looked = {r.get("karigarId") for name, r in seen.get("_all", []) if name == "get_karigar_track_record" and isinstance(r, dict)}
        wanted: list[str] = []
        for j in seen.get("list_jobs_at_risk") or []:
            if j["headKarigarId"] and _deadline_severity(j) == "critical":
                wanted.append(j["headKarigarId"])
        for p in seen.get("list_payment_delays") or []:
            wanted.append(p["karigarId"])
        todo = [k for k in dict.fromkeys(wanted) if k not in looked][:4]
        return [("get_karigar_track_record", {"karigar_id": k}) for k in todo] or None

    def finalize(seen: dict[str, Any]) -> dict[str, Any]:
        return compose_watch_report(seen.get("list_jobs_at_risk") or [], seen.get("list_payment_delays") or [])

    return RulePlanner(decide, finalize)


def _deadline_severity(j: dict[str, Any]) -> str:
    occ = j.get("daysToOccasion")
    due = j["daysToDue"]
    if (occ is not None and occ <= 3) or due < 0:
        return "critical"
    if due <= 2 or (occ is not None and occ <= 7):
        return "high"
    return "medium"


def compose_watch_report(at_risk: list[dict[str, Any]], delays: list[dict[str, Any]]) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    for j in at_risk:
        sev = _deadline_severity(j)
        when = f"due {j['dueDate']}" + (f", {j['occasionLabel'] or 'customer occasion'} on {j['occasionDate']}" if j["occasionDate"] else "")
        left = j["piecesOrdered"] - j["piecesDelivered"]
        overdue = j["daysToDue"] < 0
        alerts.append({
            "kind": "deadline",
            "severity": sev,
            "title": f"{j['code']} {'is overdue' if overdue else 'at risk'}: {left} of {j['piecesOrdered']} piece(s) outstanding",
            "detail": f"{j['title']} — {when}. " + (
                "Gold currently with " + ", ".join(f"{h['code']} {h['name']} ({h['fineGoldHeldG']:.3f} g fine)" for h in j["currentHolders"])
                if j["currentHolders"] else "No gold currently with any karigar."
            ),
            "recordId": j["jobId"],
            "karigarId": j["headKarigarId"],
        })
        for h in j["currentHolders"][:2]:
            drafts.append({
                "audience": "karigar",
                "karigarId": h["karigarId"],
                "recordId": j["jobId"],
                "channel": "whatsapp",
                "text": (
                    f"Namaste {h['name']} ji, checking on job {j['code']} ({j['title']}). "
                    + (f"The customer's {j['occasionLabel'] or 'occasion'} is on {j['occasionDate']}. " if j["occasionDate"] else "")
                    + f"It is {'past' if overdue else 'due on'} {j['dueDate']}. {left} piece(s) still to come back. "
                    "Could you share an expected delivery date, or tell us if you need anything from our side?"
                ),
            })
        if j["occasionDate"] and sev == "critical":
            drafts.append({
                "audience": "jeweller",
                "karigarId": None,
                "recordId": j["jobId"],
                "channel": "whatsapp",
                "text": f"Heads-up: {j['code']} is needed for {j['occasionLabel'] or 'a customer occasion'} on {j['occasionDate']} and {left} piece(s) are not back yet. Consider calling the customer today with an honest status.",
            })
    for p in delays:
        disputed = p["status"] == "disputed"
        days = p["daysSinceApproval"]
        sev = "high" if disputed or days > 7 else "medium"
        alerts.append({
            "kind": "dispute" if disputed else "payment",
            "severity": sev,
            "title": (f"{p['code']} disputed by {p['karigarName']}" if disputed else f"{p['karigarName']} waiting {days} day(s) for ₹{p['netPayable']:,.2f}"),
            "detail": (f"Reason given: {p['disputeReason']}" if disputed else f"Settlement {p['code']} is '{p['status']}' since approval {days} day(s) ago."),
            "recordId": p["worksheetId"],
            "karigarId": p["karigarId"],
        })
        if disputed:
            drafts.append({
                "audience": "jeweller",
                "karigarId": p["karigarId"],
                "recordId": p["worksheetId"],
                "channel": "whatsapp",
                "text": f"{p['karigarName']} disputed settlement {p['code']}: \"{(p['disputeReason'] or '')[:160]}\". Suggest re-weighing together and running the investigation agent before issuing a corrected worksheet.",
            })
        elif p["status"] == "karigar_accepted":
            drafts.append({
                "audience": "jeweller",
                "karigarId": p["karigarId"],
                "recordId": p["worksheetId"],
                "channel": "whatsapp",
                "text": f"{p['karigarName']} accepted settlement {p['code']} for ₹{p['netPayable']:,.2f}. It has been {days} day(s) since approval; please release payment and record it.",
            })
    order = {"critical": 0, "high": 1, "medium": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 3))
    crit = sum(1 for a in alerts if a["severity"] == "critical")
    summary = (
        f"{len(at_risk)} job(s) at risk ({crit} critical) and {len(delays)} karigar payment(s) outstanding."
        if alerts else "No jobs at risk and no karigar payments outstanding."
    )
    return {
        "summary": summary,
        "alerts": alerts,
        "draftMessages": drafts,
        "limitations": ["Composed by the deterministic rule-based planner from read-only tool results (no LLM).", "Drafts are not sent; a person must review and send them."],
    }


# ------------------------------------------------------------------ runner


def _clean(final: dict[str, Any], observed_ids: set[str]) -> dict[str, Any]:
    """Keep only alerts/drafts that point at records the agent actually saw."""
    out = {"summary": str(final.get("summary", ""))[:1000], "limitations": [str(x)[:300] for x in final.get("limitations", []) if x]}
    for key in ("alerts", "draftMessages"):
        items = final.get(key) if isinstance(final.get(key), list) else []
        out[key] = [i for i in items if isinstance(i, dict) and str(i.get("recordId", "")).lower() in observed_ids][:30]
    return out


def run_watcher(db: Session, user: User, horizon_days: int = 7, planner: Planner | None = None) -> AgentRun:
    org = user.organisation_id
    s = get_settings()
    llm = planner or (GeminiPlanner(s.gemini_api_key, s.gemini_model) if s.ai_provider == "gemini" and s.gemini_api_key else None)
    goal = GOAL.format(h=horizon_days)
    output: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = []
    provider = ""
    result: AgentResult | None = None

    if llm is not None:
        try:
            result = run_agent(db, org, goal=goal, system=WATCHER_SYSTEM, tools=WATCHER_TOOLS, planner=llm)
            trace = result.trace
            if result.final is None:
                raise ValueError(f"no usable answer ({result.stopped_reason})")
            ids: set[str] = set()
            from .ai_investigation import _collect_ids

            for _, args, value in result.observations:
                _collect_ids(value, ids)
            output = _clean(result.final, ids)
            provider = llm.name
        except Exception as e:
            logger.warning("LLM watcher agent failed: %s; falling back to rule planner", e)
            trace = trace + [{"type": "llm_failed", "error": str(e)[:300]}]
            output = None

    if output is None:
        rp = _rule_planner(horizon_days)
        inner = run_agent(db, org, goal=goal, system=WATCHER_SYSTEM, tools=WATCHER_TOOLS, planner=rp)
        trace = trace + inner.trace
        output = inner.final or compose_watch_report([], [])
        provider = rp.name + (" (gemini_fallback)" if llm is not None else "")

    tool_calls = [t for t in trace if t.get("type") == "tool_call"]
    output["agent"] = {
        "planner": provider,
        "toolCalls": len(tool_calls),
        "toolsUsed": sorted({t["tool"] for t in tool_calls if t.get("ok")}),
        "readOnly": True,
        "horizonDays": horizon_days,
        "sendsMessages": False,
    }
    run = AgentRun(
        organisation_id=org,
        kind="deadline_payment_watch",
        provider=provider[:60],
        output_json=json.loads(json.dumps(output, default=str)),
        trace_json=json.loads(json.dumps(trace, default=str)),
        created_by_id=user.id,
    )
    db.add(run)
    db.flush()
    audit.record(db, user, org, "agent.watch_completed", "agent_run", run.id, {"alerts": len(output.get("alerts", [])), "drafts": len(output.get("draftMessages", [])), "provider": run.provider})
    return run
