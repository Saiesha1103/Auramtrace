"""Agent runtime: a bounded tool-calling loop shared by every AURUMTRACE agent.

How it works
  1. The agent gets a goal and a registry of READ-ONLY tools.
  2. A planner (Gemini function calling, or the deterministic rule-based planner) decides which
     tool to call next, looking at everything it has observed so far.
  3. The runtime validates the arguments, runs the tool scoped to the caller's organisation, and
     feeds the result back. This repeats until the planner returns a final answer or hits
     ``max_steps``.
  4. Every step is recorded in a trace that is persisted alongside the result, so a person can
     audit exactly what the agent looked at.

Safety boundaries (enforced here, not by prompting):
  * Only tools in the registry can run, and every registered tool is read-only.
  * Tool arguments are validated (ids must be UUIDs); organisation scoping is injected by the
    runtime, never taken from the model.
  * Step count, tool-result size and HTTP time are bounded.
  * Agents produce proposals and drafts only. Nothing they output is sent, approved or posted.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from ..errors import AppError

logger = logging.getLogger("aurumtrace.agent")

MAX_RESULT_CHARS = 12_000
DEFAULT_MAX_STEPS = 8


# ------------------------------------------------------------------ tools


@dataclass(frozen=True)
class ToolParam:
    name: str
    kind: str  # "uuid" | "integer" | "string"
    description: str
    required: bool = True


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: tuple[ToolParam, ...]
    fn: Callable[..., Any]  # fn(db, org_id, **validated_args)

    def declaration(self) -> dict[str, Any]:
        """Gemini functionDeclaration."""
        props = {
            p.name: {"type": "INTEGER" if p.kind == "integer" else "STRING", "description": p.description}
            for p in self.params
        }
        decl: dict[str, Any] = {"name": self.name, "description": self.description}
        if props:
            decl["parameters"] = {"type": "OBJECT", "properties": props, "required": [p.name for p in self.params if p.required]}
        return decl


class ToolArgumentError(ValueError):
    pass


def _validate_args(tool: Tool, raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(raw or {})
    out: dict[str, Any] = {}
    for p in tool.params:
        if p.name not in raw or raw[p.name] in (None, ""):
            if p.required:
                raise ToolArgumentError(f"missing required argument '{p.name}'")
            continue
        v = raw.pop(p.name)
        if p.kind == "uuid":
            try:
                out[p.name] = uuid.UUID(str(v))
            except ValueError:
                raise ToolArgumentError(f"argument '{p.name}' must be a UUID")
        elif p.kind == "integer":
            try:
                out[p.name] = max(0, min(int(v), 365))
            except (TypeError, ValueError):
                raise ToolArgumentError(f"argument '{p.name}' must be an integer")
        else:
            out[p.name] = str(v)[:200]
    if raw:
        raise ToolArgumentError(f"unexpected arguments: {sorted(raw)}")
    return out


def _clip(result: Any) -> Any:
    text = json.dumps(result, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return result
    return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}


# ------------------------------------------------------------------ planners


class Planner(Protocol):
    """Decides the next move. Given the conversation so far, returns one model turn:
    ``{"role": "model", "parts": [...]}`` whose parts are ``functionCall`` and/or ``text``."""

    name: str

    def next_turn(self, system: str, contents: list[dict[str, Any]], tools: list[Tool]) -> dict[str, Any]: ...


class GeminiPlanner:
    """Gemini function-calling planner over the REST API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", timeout: float = 20.0, transport: Any = None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport  # httpx transport, injectable for tests
        self.name = f"gemini_{model}"

    def next_turn(self, system: str, contents: list[dict[str, Any]], tools: list[Tool]) -> dict[str, Any]:
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": [t.declaration() for t in tools]}],
            "generationConfig": {"temperature": 0.1},
        }
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        with httpx.Client(**kwargs) as client:
            # key in a header, not the URL, so it never lands in proxy/access logs
            res = client.post(url, json=payload, headers={"x-goog-api-key": self.api_key})
            res.raise_for_status()
            data = res.json()
        content = data["candidates"][0]["content"]
        content.setdefault("role", "model")
        return content


# ------------------------------------------------------------------ loop


@dataclass
class AgentResult:
    final: dict[str, Any] | None
    trace: list[dict[str, Any]] = field(default_factory=list)
    observations: list[tuple[str, dict[str, Any], Any]] = field(default_factory=list)
    stopped_reason: str = "final_answer"


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of model text (tolerates ```json fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None


def run_agent(
    db: Session,
    org_id: uuid.UUID,
    *,
    goal: str,
    system: str,
    tools: list[Tool],
    planner: Planner,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> AgentResult:
    """Run the plan → act → observe loop. Raises only if the planner itself fails (e.g. network)."""
    registry = {t.name: t for t in tools}
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": goal}]}]
    result = AgentResult(final=None)

    for step in range(1, max_steps + 1):
        turn = planner.next_turn(system, contents, tools)
        contents.append(turn)
        parts = turn.get("parts") or []
        calls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
        if not calls:
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            result.final = extract_json(text)
            result.stopped_reason = "final_answer" if result.final is not None else "unparseable_answer"
            result.trace.append({"step": step, "type": "final", "ok": result.final is not None})
            return result

        responses = []
        for call in calls:
            name = call.get("name", "")
            raw_args = call.get("args") or {}
            entry: dict[str, Any] = {"step": step, "type": "tool_call", "tool": name, "args": raw_args}
            tool = registry.get(name)
            if tool is None:
                payload: Any = {"error": f"unknown tool '{name}'. Available: {sorted(registry)}"}
                entry["ok"] = False
            else:
                try:
                    args = _validate_args(tool, raw_args)
                    value = tool.fn(db, org_id, **args)
                    payload = {"result": _clip(value)}
                    result.observations.append((name, {k: str(v) for k, v in args.items()}, value))
                    entry["ok"] = True
                    entry["summary"] = _summarise(value)
                except ToolArgumentError as e:
                    payload = {"error": str(e)}
                    entry["ok"] = False
                except AppError as e:  # NotFound for other-org / missing records, etc.
                    payload = {"error": e.message}
                    entry["ok"] = False
            if not entry["ok"]:
                entry["error"] = payload["error"]
            result.trace.append(entry)
            responses.append({"functionResponse": {"name": name, "response": payload}})
        contents.append({"role": "user", "parts": responses})

    result.stopped_reason = "max_steps"
    return result


def _summarise(value: Any) -> str:
    if isinstance(value, list):
        return f"{len(value)} record(s)"
    if isinstance(value, dict):
        if "code" in value:
            return f"record {value['code']}"
        return f"{len(value)} field(s)"
    if value is None:
        return "no record"
    return type(value).__name__


# ------------------------------------------------------------------ deterministic planner


class RulePlanner:
    """A deterministic planner used when no LLM is configured (or it fails).

    It still runs through the same loop and tool registry: ``decide`` looks at the observations
    so far and returns the next tool calls, or ``None`` when it has enough to answer; then
    ``finalize`` composes the answer from what was observed.
    """

    name = "rule_planner_v1"

    def __init__(
        self,
        decide: Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]] | None],
        finalize: Callable[[dict[str, Any]], dict[str, Any]],
    ):
        self.decide = decide
        self.finalize = finalize
        self.seen: dict[str, Any] = {}

    def next_turn(self, system: str, contents: list[dict[str, Any]], tools: list[Tool]) -> dict[str, Any]:
        # absorb the latest tool responses into `seen` (keyed "tool" and "tool:arg")
        last = contents[-1]
        for p in last.get("parts", []):
            fr = p.get("functionResponse") if isinstance(p, dict) else None
            if fr and "result" in fr["response"]:
                self.seen.setdefault(fr["name"], fr["response"]["result"])
                self.seen.setdefault("_all", []).append((fr["name"], fr["response"]["result"]))
        calls = self.decide(self.seen)
        if calls:
            return {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}} for n, a in calls]}
        return {"role": "model", "parts": [{"text": json.dumps(self.finalize(self.seen), default=str)}]}
