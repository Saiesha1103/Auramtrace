"""Phase 1 data model (PRD §8 core entities).

Custody is never stored as a mutable balance: every gram is accounted for by
append-only MaterialEvent rows, and balances are derived from them.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import Fineness, Grams, created_at_col, str_enum, utcnow, uuid_pk
from .enums import (
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


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    users: Mapped[list["User"]] = relationship(back_populates="organisation")
    karigars: Mapped[list["Karigar"]] = relationship(back_populates="organisation")
    jobs: Mapped[list["JobOrder"]] = relationship(back_populates="organisation")
    lots: Mapped[list["MaterialLot"]] = relationship(back_populates="organisation")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    organisation: Mapped[Organisation] = relationship(back_populates="users")


class Karigar(Base):
    __tablename__ = "karigars"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_karigar_code_per_org"),
        CheckConstraint("head_karigar_id IS NULL OR head_karigar_id <> id", name="ck_karigar_not_own_head"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[KarigarKind] = mapped_column(str_enum(KarigarKind), nullable=False)
    head_karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), nullable=True, index=True)
    unit: Mapped[str | None] = mapped_column(String(160))
    contact: Mapped[str | None] = mapped_column(String(80))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[KarigarStatus] = mapped_column(str_enum(KarigarStatus), default=KarigarStatus.active, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    organisation: Mapped[Organisation] = relationship(back_populates="karigars")
    head_karigar: Mapped["Karigar | None"] = relationship(remote_side="Karigar.id", back_populates="team")
    team: Mapped[list["Karigar"]] = relationship(back_populates="head_karigar")


class JobOrder(Base):
    __tablename__ = "job_orders"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_job_code_per_org"),
        CheckConstraint("pieces > 0", name="ck_job_pieces_positive"),
        CheckConstraint("loss_allowance_pct >= 0 AND loss_allowance_pct <= 5", name="ck_job_allowance_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    order_ref: Mapped[str | None] = mapped_column(String(60))
    process: Mapped[str | None] = mapped_column(String(120))
    karat: Mapped[Karat] = mapped_column(str_enum(Karat, 8), nullable=False)
    target_fineness_ppt: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    pieces: Mapped[int] = mapped_column(nullable=False)
    target_gross_per_piece_g: Mapped[Decimal | None] = mapped_column(Grams)
    loss_allowance_pct: Mapped[Decimal] = mapped_column(Fineness, nullable=False, default=Decimal("1.0"))
    contract_version: Mapped[str | None] = mapped_column(String(40))
    head_karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus), default=JobStatus.draft, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    organisation: Mapped[Organisation] = relationship(back_populates="jobs")
    head_karigar: Mapped[Karigar | None] = relationship(foreign_keys=[head_karigar_id])


class MaterialLot(Base):
    """A physical lot of metal received into the vault. Its weights here are the receipt reading;
    current location/quantity is derived from MaterialEvent rows, never stored."""

    __tablename__ = "material_lots"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_lot_code_per_org"),
        CheckConstraint("gross_weight_g > 0", name="ck_lot_gross_positive"),
        CheckConstraint("net_weight_g > 0 AND net_weight_g <= gross_weight_g", name="ck_lot_net_within_gross"),
        CheckConstraint("fineness_ppt > 0 AND fineness_ppt <= 999.9", name="ck_lot_fineness_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    metal_type: Mapped[MetalType] = mapped_column(str_enum(MetalType, 16), default=MetalType.gold, nullable=False)
    source: Mapped[str | None] = mapped_column(String(160))  # bar / refinery / supplier reference
    gross_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    net_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    stone_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    fineness_ppt: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    fine_gold_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    organisation: Mapped[Organisation] = relationship(back_populates="lots")
    source_job: Mapped[JobOrder | None] = relationship()
    events: Mapped[list["MaterialEvent"]] = relationship(back_populates="lot", order_by="MaterialEvent.recorded_at")


class MaterialEvent(Base):
    """APPEND-ONLY custody ledger. Rows are never updated or deleted (enforced in the ORM and by DB triggers).
    Corrections are new `reversal` rows that mirror the original movement and reference it."""

    __tablename__ = "material_events"
    __table_args__ = (
        UniqueConstraint("ref_event_id", "event_type", name="uq_one_followup_per_event_type"),
        CheckConstraint("gross_weight_g IS NULL OR gross_weight_g > 0", name="ck_event_gross_positive"),
        CheckConstraint("net_weight_g IS NULL OR (net_weight_g > 0 AND net_weight_g <= gross_weight_g)", name="ck_event_net_within_gross"),
        Index("ix_material_events_org_time", "organisation_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type: Mapped[MaterialEventType] = mapped_column(str_enum(MaterialEventType), nullable=False, index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_lots.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), index=True)

    from_type: Mapped[CustodianType | None] = mapped_column(str_enum(CustodianType, 16))
    from_karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), index=True)
    to_type: Mapped[CustodianType | None] = mapped_column(str_enum(CustodianType, 16))
    to_karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), index=True)

    gross_weight_g: Mapped[Decimal | None] = mapped_column(Grams)
    net_weight_g: Mapped[Decimal | None] = mapped_column(Grams)
    fineness_ppt: Mapped[Decimal | None] = mapped_column(Fineness)
    fine_gold_g: Mapped[Decimal | None] = mapped_column(Grams)

    # provenance (PRD: evidence-grade weighing)
    scale_id: Mapped[str | None] = mapped_column(String(60))
    operator_name: Mapped[str | None] = mapped_column(String(120))
    measurement_method: Mapped[MeasurementMethod | None] = mapped_column(str_enum(MeasurementMethod, 16))
    challan_ref: Mapped[str | None] = mapped_column(String(60))
    evidence_ref: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)

    #: for issue_acknowledged → the issue; for reversal → the event being reversed
    ref_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_events.id", ondelete="RESTRICT"), index=True)
    acknowledged_by_name: Mapped[str | None] = mapped_column(String(120))

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    lot: Mapped[MaterialLot] = relationship(back_populates="events")
    job: Mapped[JobOrder | None] = relationship()
    from_karigar: Mapped[Karigar | None] = relationship(foreign_keys=[from_karigar_id])
    to_karigar: Mapped[Karigar | None] = relationship(foreign_keys=[to_karigar_id])
    ref_event: Mapped["MaterialEvent | None"] = relationship(remote_side="MaterialEvent.id")
    recorded_by: Mapped[User] = relationship()


class AuditEvent(Base):
    """APPEND-ONLY audit trail of every write (who did what, to which record, with which values)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_time", "organisation_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    actor: Mapped[User | None] = relationship()
