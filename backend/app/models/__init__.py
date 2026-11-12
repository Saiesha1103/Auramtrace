"""Models + append-only enforcement.

History tables (material_events, audit_events) are protected twice:
  1. ORM: flushing an UPDATE or DELETE of a loaded row raises AppendOnlyViolation.
  2. Database: BEFORE UPDATE/DELETE triggers reject the statement even from raw SQL
     (PostgreSQL function + triggers, or SQLite RAISE(ABORT) triggers). The same DDL is in
     the Alembic baseline migration.
"""

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session

from ..database import Base
from ..errors import AppendOnlyViolation
from .entities import AuditEvent, Karigar, JobOrder, MaterialEvent, MaterialLot, Organisation, User
from .enums import (
    MOVEMENT_EVENTS,
    CustodianType,
    JobStatus,
    Karat,
    KarigarKind,
    KarigarStatus,
    MaterialEventType,
    MeasurementMethod,
    MetalType,
    UserRole,
)

APPEND_ONLY_TABLES = ("material_events", "audit_events")
APPEND_ONLY_MODELS = (MaterialEvent, AuditEvent)

PG_FUNCTION = """
CREATE OR REPLACE FUNCTION aurum_forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table %: % is not allowed', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql
"""


def pg_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION aurum_forbid_mutation()"
    )


def sqlite_triggers(table: str) -> list[str]:
    return [
        f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only table {table}: UPDATE is not allowed'); END",
        f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append-only table {table}: DELETE is not allowed'); END",
    ]


# --- database layer -------------------------------------------------------
# DDL() applies %-formatting, so PL/pgSQL's % placeholders are escaped here (raw SQL is used as-is by Alembic)
event.listen(Base.metadata, "before_create", DDL(PG_FUNCTION.replace("%", "%%")).execute_if(dialect="postgresql"))
for _model in APPEND_ONLY_MODELS:
    _table = _model.__table__
    event.listen(_table, "after_create", DDL(pg_trigger(_table.name)).execute_if(dialect="postgresql"))
    for _stmt in sqlite_triggers(_table.name):
        event.listen(_table, "after_create", DDL(_stmt).execute_if(dialect="sqlite"))


# --- ORM layer -------------------------------------------------------------
@event.listens_for(Session, "before_flush")
def _forbid_history_mutation(session: Session, _ctx, _instances) -> None:
    for obj in session.dirty:
        if isinstance(obj, APPEND_ONLY_MODELS) and session.is_modified(obj, include_collections=False):
            raise AppendOnlyViolation(f"{type(obj).__name__} rows are append-only; record a reversal event instead")
    for obj in session.deleted:
        if isinstance(obj, APPEND_ONLY_MODELS):
            raise AppendOnlyViolation(f"{type(obj).__name__} rows cannot be deleted")


__all__ = [
    "Base",
    "Organisation",
    "User",
    "Karigar",
    "JobOrder",
    "MaterialLot",
    "MaterialEvent",
    "AuditEvent",
    "UserRole",
    "KarigarKind",
    "KarigarStatus",
    "JobStatus",
    "Karat",
    "MetalType",
    "MeasurementMethod",
    "CustodianType",
    "MaterialEventType",
    "MOVEMENT_EVENTS",
    "APPEND_ONLY_TABLES",
    "PG_FUNCTION",
    "pg_trigger",
    "sqlite_triggers",
]
