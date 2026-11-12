"""Request / response schemas for Phase 1 resources."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from ..models.enums import CustodianType, JobStatus, Karat, KarigarKind, KarigarStatus, MaterialEventType, MetalType, UserRole
from .common import CamelModel, Fineness, Grams, MeasurementIn, MeasurementOut, Quantity, UtcDateTime

KARAT_FINENESS = {Karat.k24: Decimal("995.0"), Karat.k22: Decimal("916.0"), Karat.k18: Decimal("750.0"), Karat.k14: Decimal("585.0")}

# ----------------------------------------------------------------- auth / users


class UserOut(CamelModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: UtcDateTime


class RegisterRequest(CamelModel):
    organisation_name: str = Field(min_length=2, max_length=160, examples=["Demo Jewellers (synthetic)"])
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(CamelModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
    user: UserOut


class UserCreate(CamelModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: UserRole
    password: str = Field(min_length=10, max_length=128)


class UserUpdate(CamelModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    role: UserRole | None = None
    is_active: bool | None = None


class OrganisationOut(CamelModel):
    id: uuid.UUID
    name: str
    created_at: UtcDateTime


class OrganisationUpdate(CamelModel):
    name: str = Field(min_length=2, max_length=160)


# ----------------------------------------------------------------- karigars


class KarigarRef(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    kind: KarigarKind


class KarigarCreate(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=24, pattern=r"^[A-Za-z0-9-]+$", description="Optional; generated as K-0001… if omitted")
    name: str = Field(min_length=2, max_length=160)
    kind: KarigarKind
    head_karigar_id: uuid.UUID | None = None
    unit: str | None = Field(default=None, max_length=160)
    contact: str | None = Field(default=None, max_length=80)
    skills: list[str] = Field(default_factory=list, max_length=20)


class KarigarUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    head_karigar_id: uuid.UUID | None = None
    unit: str | None = Field(default=None, max_length=160)
    contact: str | None = Field(default=None, max_length=80)
    skills: list[str] | None = Field(default=None, max_length=20)
    status: KarigarStatus | None = None


class KarigarOut(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    kind: KarigarKind
    head_karigar_id: uuid.UUID | None
    unit: str | None
    contact: str | None
    skills: list[str]
    status: KarigarStatus
    created_at: UtcDateTime


class JobHolding(CamelModel):
    job_id: uuid.UUID | None
    job_code: str | None
    fine_gold_g: Grams
    net_weight_g: Grams


class CustodySummary(CamelModel):
    """Derived from the append-only event ledger — never stored."""

    fine_gold_g: Grams
    net_weight_g: Grams
    gross_weight_g: Grams
    pending_acknowledgements: int
    by_job: list[JobHolding]


class KarigarProfile(KarigarOut):
    head_karigar: KarigarRef | None
    team: list[KarigarRef]
    custody: CustodySummary
    recent_events: list["EventOut"]


class HierarchyNode(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    kind: KarigarKind
    status: KarigarStatus
    fine_gold_held_g: Grams
    children: list["HierarchyNode"]


# ----------------------------------------------------------------- jobs


class JobCreate(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=24, pattern=r"^[A-Za-z0-9-]+$", description="Optional; generated as J-0001… if omitted")
    title: str = Field(min_length=2, max_length=200)
    order_ref: str | None = Field(default=None, max_length=60)
    process: str | None = Field(default=None, max_length=120)
    karat: Karat
    target_fineness_ppt: Fineness | None = Field(default=None, description="Defaults from karat: 24K→995, 22K→916, 18K→750, 14K→585")
    pieces: int = Field(gt=0, le=100000)
    target_gross_per_piece_g: Grams | None = None
    loss_allowance_pct: Decimal = Field(default=Decimal("1.0"), ge=0, le=5, decimal_places=1)
    contract_version: str | None = Field(default=None, max_length=40)
    head_karigar_id: uuid.UUID | None = None
    due_date: date
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("target_gross_per_piece_g")
    @classmethod
    def _positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("Target gross per piece must be greater than zero")
        return v

    @model_validator(mode="after")
    def _default_fineness(self) -> "JobCreate":
        if self.target_fineness_ppt is None:
            self.target_fineness_ppt = KARAT_FINENESS[self.karat]
        return self


class JobUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    order_ref: str | None = Field(default=None, max_length=60)
    process: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    head_karigar_id: uuid.UUID | None = None
    status: Literal["cancelled"] | None = Field(default=None, description="Phase 1 only allows cancelling a job that has no gold issued")


class JobOut(CamelModel):
    id: uuid.UUID
    code: str
    title: str
    order_ref: str | None
    process: str | None
    karat: Karat
    target_fineness_ppt: Fineness
    pieces: int
    target_gross_per_piece_g: Grams | None
    loss_allowance_pct: Decimal
    contract_version: str | None
    head_karigar_id: uuid.UUID | None
    due_date: date
    notes: str | None
    status: JobStatus
    created_at: UtcDateTime


class JobCustodyLine(CamelModel):
    karigar_id: uuid.UUID
    karigar_code: str
    karigar_name: str
    fine_gold_g: Grams
    net_weight_g: Grams


class JobDetail(JobOut):
    issued: Quantity
    pending_acknowledgements: int
    custody: list[JobCustodyLine]
    events: list["EventOut"]


# ----------------------------------------------------------------- lots & events


class LotCreate(CamelModel):
    code: str | None = Field(default=None, min_length=1, max_length=24, pattern=r"^[A-Za-z0-9-]+$", description="Optional; generated as L-0001… if omitted")
    metal_type: MetalType = MetalType.gold
    source: str | None = Field(default=None, max_length=160, examples=["Bar 995 · B-792"])
    gross_weight_g: Grams = Field(examples=[30.151])
    net_weight_g: Grams = Field(examples=[30.151], description="Metal only (gross − stones/non-metal)")
    fineness_ppt: Fineness = Field(examples=[995.0])
    source_job_id: uuid.UUID | None = None
    measurement: MeasurementIn
    challan_ref: str | None = Field(default=None, max_length=60)
    evidence_ref: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _weights(self) -> "LotCreate":
        if self.gross_weight_g <= 0 or self.net_weight_g <= 0:
            raise ValueError("Weights must be greater than zero")
        if self.net_weight_g > self.gross_weight_g:
            raise ValueError("Net metal weight cannot exceed gross weight")
        return self


class LotBalance(CamelModel):
    vault: Quantity
    with_karigars: Quantity


class LotOut(CamelModel):
    id: uuid.UUID
    code: str
    metal_type: MetalType
    source: str | None
    gross_weight_g: Grams
    net_weight_g: Grams
    stone_weight_g: Grams
    fineness_ppt: Fineness
    fine_gold_g: Grams
    source_job_id: uuid.UUID | None
    created_at: UtcDateTime
    balance: LotBalance | None = None


class IssueRequest(CamelModel):
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    gross_weight_g: Grams = Field(examples=[30.151])
    net_weight_g: Grams = Field(examples=[30.151])
    measurement: MeasurementIn
    challan_ref: str | None = Field(default=None, max_length=60, examples=["JWC-26-3301"])
    evidence_ref: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _weights(self) -> "IssueRequest":
        if self.gross_weight_g <= 0 or self.net_weight_g <= 0:
            raise ValueError("Weights must be greater than zero")
        if self.net_weight_g > self.gross_weight_g:
            raise ValueError("Net metal weight cannot exceed gross weight")
        return self


class AcknowledgeRequest(CamelModel):
    acknowledged_by_name: str = Field(min_length=2, max_length=120, description="Person who signed for the metal")
    evidence_ref: str | None = Field(default=None, max_length=200, examples=["ACK-3301 signed slip photo"])
    note: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None


class ReverseRequest(CamelModel):
    reason: str = Field(min_length=5, max_length=2000, examples=["Wrong lot selected at issue; re-issuing from L-0002"])


class CustodianOut(CamelModel):
    type: CustodianType | None
    karigar_id: uuid.UUID | None = None
    karigar_code: str | None = None
    karigar_name: str | None = None


class EventState(CamelModel):
    reversed: bool
    reversal_event_id: uuid.UUID | None
    acknowledged: bool | None = Field(description="Only for issue events; null otherwise")
    acknowledgement_event_id: uuid.UUID | None


class UserRef(CamelModel):
    id: uuid.UUID
    full_name: str


class EventOut(CamelModel):
    id: uuid.UUID
    event_type: MaterialEventType
    lot_id: uuid.UUID
    lot_code: str
    job_id: uuid.UUID | None
    job_code: str | None
    from_: CustodianOut = Field(alias="from")
    to: CustodianOut
    gross_weight_g: Grams | None
    net_weight_g: Grams | None
    fineness_ppt: Fineness | None
    fine_gold_g: Grams | None
    measurement: MeasurementOut | None
    challan_ref: str | None
    evidence_ref: str | None
    note: str | None
    ref_event_id: uuid.UUID | None
    acknowledged_by_name: str | None
    occurred_at: UtcDateTime
    recorded_at: UtcDateTime
    recorded_by: UserRef
    state: EventState


class AuditOut(CamelModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    created_at: UtcDateTime


KarigarProfile.model_rebuild()
JobDetail.model_rebuild()
HierarchyNode.model_rebuild()
