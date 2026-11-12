"""Shared column helpers."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


#: grams, 0.001 g resolution
Grams = Numeric(14, 3)
#: fineness in parts per thousand, 0.1 resolution (e.g. 916.0, 995.0, 999.9)
Fineness = Numeric(5, 1)


def str_enum(enum_cls: type, length: int = 32) -> SAEnum:
    """Store enum values as plain strings (no native DB enum) so later phases can add values without a type migration."""
    return SAEnum(enum_cls, native_enum=False, create_constraint=False, length=length, values_callable=lambda e: [m.value for m in e])


def code_col(length: int = 24) -> Mapped[str]:
    return mapped_column(String(length), nullable=False)


__all__ = ["Decimal", "Grams", "Fineness", "uuid_pk", "created_at_col", "str_enum", "code_col", "utcnow"]
