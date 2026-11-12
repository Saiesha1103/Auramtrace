"""Human-readable per-organisation codes (K-0001, J-0001, L-0001)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import Conflict


def ensure_unique_code(db: Session, model, organisation_id: uuid.UUID, code: str) -> str:
    exists = db.scalar(select(func.count()).select_from(model).where(model.organisation_id == organisation_id, model.code == code))
    if exists:
        raise Conflict(f"Code {code} is already used in this organisation", code="duplicate_code")
    return code


def next_code(db: Session, model, organisation_id: uuid.UUID, prefix: str) -> str:
    n = db.scalar(select(func.count()).select_from(model).where(model.organisation_id == organisation_id)) or 0
    while True:
        n += 1
        code = f"{prefix}-{n:04d}"
        taken = db.scalar(select(func.count()).select_from(model).where(model.organisation_id == organisation_id, model.code == code))
        if not taken:
            return code
