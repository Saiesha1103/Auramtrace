"""Append-only audit trail writer."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent, User


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (uuid.UUID, datetime, date)):
        return str(v)
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def record(db: Session, actor: User | None, organisation_id: uuid.UUID, action: str, entity_type: str, entity_id: Any, details: dict | None = None) -> AuditEvent:
    ev = AuditEvent(
        organisation_id=organisation_id,
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=_jsonable(details or {}),
    )
    db.add(ev)
    return ev
