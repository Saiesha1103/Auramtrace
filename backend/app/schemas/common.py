"""Shared schema building blocks.

JSON conventions (stable contract with the TypeScript frontend):
  * field names are camelCase (snake_case is also accepted on input)
  * weights are JSON numbers in grams with at most 3 decimals (e.g. 30.151); more decimals are rejected
  * fineness is parts per thousand (916.0 = 22K), at most 1 decimal
  * timestamps are ISO-8601 UTC with a trailing "Z"; plain dates are YYYY-MM-DD
  * ids are UUID strings; human-readable codes (K-0001, J-0001, L-0001) are separate fields
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

from ..models.enums import MeasurementMethod
from ..services.fine_gold import to_grams, validate_fineness


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


def _utc_iso(d: datetime) -> str:
    if d.tzinfo is None:  # SQLite returns naive values; they are stored as UTC
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


Grams = Annotated[Decimal, BeforeValidator(to_grams), PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
Fineness = Annotated[Decimal, BeforeValidator(validate_fineness), PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
UtcDateTime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str, when_used="json")]

T = TypeVar("T")


class Page(CamelModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str = Field(examples=["insufficient_balance"])
    message: str = Field(examples=["Lot L-0001 has only 12.500 g net metal in the vault"])
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class MeasurementIn(CamelModel):
    """Provenance of a weighing (PRD: evidence-grade weighing)."""

    scale_id: str = Field(min_length=1, max_length=60, examples=["SC-01"])
    operator_name: str = Field(min_length=1, max_length=120, examples=["Vault desk"])
    method: MeasurementMethod = MeasurementMethod.manual


class MeasurementOut(CamelModel):
    scale_id: str | None
    operator_name: str | None
    method: MeasurementMethod | None


class Quantity(CamelModel):
    gross_weight_g: Grams
    net_weight_g: Grams
    fine_gold_g: Grams


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token"},
    403: {"model": ErrorResponse, "description": "Role not permitted"},
    404: {"model": ErrorResponse, "description": "Not found in your organisation"},
    409: {"model": ErrorResponse, "description": "Conflict (duplicate, already acknowledged/reversed, append-only)"},
    422: {"model": ErrorResponse, "description": "Validation error or custody rule violation"},
}
