"""Proactive agents (advisory only): the deadline & payment watcher."""

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from ..deps import DB, CurrentUser, Manager
from ..models import AgentRun
from ..schemas import ERROR_RESPONSES, CamelModel, Page, UtcDateTime
from ..services.custody import get_in_org
from ..services.watcher_agent import run_watcher

router = APIRouter(prefix="/agents", tags=["agents"], responses=ERROR_RESPONSES)


class WatchRequest(CamelModel):
    horizon_days: int = Field(default=7, ge=0, le=60)


class AgentRunOut(CamelModel):
    id: uuid.UUID
    kind: str
    provider: str
    output: dict[str, Any]
    trace: list[dict[str, Any]]
    created_at: UtcDateTime


def _out(r: AgentRun) -> AgentRunOut:
    return AgentRunOut(id=r.id, kind=r.kind, provider=r.provider, output=r.output_json, trace=r.trace_json, created_at=r.created_at)


@router.post("/watch", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED, summary="Run the deadline & payment watcher agent (admin, manager)")
def post_watch(body: WatchRequest, user: Manager, db: DB) -> AgentRunOut:
    """The agent checks open jobs against due and customer occasion dates, and approved-but-unpaid
    karigar settlements, then proposes alerts and DRAFT messages. It sends nothing."""
    run = run_watcher(db, user, body.horizon_days)
    db.commit()
    return _out(run)


@router.get("/runs", response_model=Page[AgentRunOut], summary="Past agent runs, newest first")
def list_runs(user: CurrentUser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> Page[AgentRunOut]:
    q = select(AgentRun).where(AgentRun.organisation_id == user.organisation_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset))
    return Page(items=[_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=AgentRunOut, summary="One agent run with its full tool trace")
def get_run(run_id: uuid.UUID, user: CurrentUser, db: DB) -> AgentRunOut:
    return _out(get_in_org(db, AgentRun, user.organisation_id, run_id, "Agent run"))
