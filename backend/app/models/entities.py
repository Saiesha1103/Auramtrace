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
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    JobStatus,
    Karat,
    KarigarKind,
    KarigarStatus,
    MaterialEventType,
    MeasurementMethod,
    MetalType,
    ProductionStatus,
    ReconciliationStatus,
    ReturnCategory,
    SettlementStatus,
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
        CheckConstraint("parent_job_id IS NULL OR parent_job_id <> id", name="ck_job_not_own_parent"),
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
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=True, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus), default=JobStatus.draft, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    organisation: Mapped[Organisation] = relationship(back_populates="jobs")
    head_karigar: Mapped[Karigar | None] = relationship(foreign_keys=[head_karigar_id])
    parent_job: Mapped["JobOrder | None"] = relationship(remote_side="JobOrder.id", back_populates="child_jobs")
    child_jobs: Mapped[list["JobOrder"]] = relationship(back_populates="parent_job")


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


class JobSplit(Base):
    """Parent-child job split tracking."""

    __tablename__ = "job_splits"
    __table_args__ = (
        UniqueConstraint("child_job_id", name="uq_child_job_split"),
        CheckConstraint("allocated_pieces > 0", name="ck_split_pieces_positive"),
        CheckConstraint("allocated_gross_weight_g IS NULL OR allocated_gross_weight_g > 0", name="ck_split_gross_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    parent_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    child_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    allocated_pieces: Mapped[int] = mapped_column(nullable=False)
    allocated_gross_weight_g: Mapped[Decimal | None] = mapped_column(Grams)
    split_reason: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    parent_job: Mapped[JobOrder] = relationship(foreign_keys=[parent_job_id])
    child_job: Mapped[JobOrder] = relationship(foreign_keys=[child_job_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])


class ProductionEntry(Base):
    """Production stage/phase execution record for a job."""

    __tablename__ = "production_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    karigar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[ProductionStatus] = mapped_column(str_enum(ProductionStatus), default=ProductionStatus.in_progress, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    job: Mapped[JobOrder] = relationship()
    karigar: Mapped[Karigar] = relationship()
    created_by: Mapped[User] = relationship()
    measurements: Mapped[list["ProductionMeasurement"]] = relationship(back_populates="production_entry")


class ProductionMeasurement(Base):
    """Immutable physical measurements recorded during manufacturing.
    Does not move custody directly — corrections are recorded as superseding measurements."""

    __tablename__ = "production_measurements"
    __table_args__ = (
        CheckConstraint("input_gross_weight_g >= input_net_metal_weight_g", name="ck_pm_input_gross_ge_net"),
        CheckConstraint("output_gross_weight_g >= output_net_metal_weight_g", name="ck_pm_output_gross_ge_net"),
        CheckConstraint("fineness_ppt > 0 AND fineness_ppt <= 999.9", name="ck_pm_fineness_range"),
        CheckConstraint("input_gross_weight_g > 0", name="ck_pm_input_gross_pos"),
        CheckConstraint("output_gross_weight_g > 0", name="ck_pm_output_gross_pos"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    production_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("production_entries.id", ondelete="RESTRICT"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    karigar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(60), nullable=False)

    input_gross_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    input_net_metal_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    output_gross_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    output_net_metal_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    stone_weight_g: Mapped[Decimal] = mapped_column(Grams, default=Decimal("0.000"), nullable=False)
    alloy_weight_g: Mapped[Decimal] = mapped_column(Grams, default=Decimal("0.000"), nullable=False)
    fineness_ppt: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    pieces: Mapped[int] = mapped_column(nullable=False, default=1)

    scale_id: Mapped[str | None] = mapped_column(String(60))
    operator_name: Mapped[str | None] = mapped_column(String(120))
    measurement_method: Mapped[MeasurementMethod | None] = mapped_column(str_enum(MeasurementMethod, 16))
    evidence_ref: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    # Audited correction/superseding support
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("production_measurements.id", ondelete="RESTRICT"))
    correction_reason: Mapped[str | None] = mapped_column(String(250))

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    production_entry: Mapped[ProductionEntry | None] = relationship(back_populates="measurements")
    job: Mapped[JobOrder] = relationship()
    karigar: Mapped[Karigar] = relationship()
    recorded_by: Mapped[User] = relationship(foreign_keys=[recorded_by_id])
    superseded_by: Mapped["ProductionMeasurement | None"] = relationship(remote_side="ProductionMeasurement.id")


class MaterialReturn(Base):
    """Material return record (finished jewellery, scrap, dust, WIP) from a karigar back to the vault.
    Backed by an immutable MaterialEvent (return_vault) row in the custody ledger."""

    __tablename__ = "material_returns"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_return_code_per_org"),
        CheckConstraint("gross_weight_g > 0", name="ck_return_gross_positive"),
        CheckConstraint("net_metal_weight_g > 0 AND net_metal_weight_g <= gross_weight_g", name="ck_return_net_within_gross"),
        CheckConstraint("declared_fineness_ppt > 0 AND declared_fineness_ppt <= 999.9", name="ck_return_declared_fineness_range"),
        CheckConstraint("assayed_fineness_ppt IS NULL OR (assayed_fineness_ppt > 0 AND assayed_fineness_ppt <= 999.9)", name="ck_return_assayed_fineness_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    karigar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), nullable=False, index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_lots.id", ondelete="RESTRICT"), nullable=False, index=True)

    return_category: Mapped[ReturnCategory] = mapped_column(str_enum(ReturnCategory), nullable=False, index=True)
    gross_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    net_metal_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    stone_weight_g: Mapped[Decimal] = mapped_column(Grams, default=Decimal("0.000"), nullable=False)
    declared_fineness_ppt: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    assayed_fineness_ppt: Mapped[Decimal | None] = mapped_column(Fineness)
    fine_gold_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    pieces: Mapped[int] = mapped_column(nullable=False, default=1)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retained_scrap_g: Mapped[Decimal] = mapped_column(Grams, default=Decimal("0.000"), nullable=False)

    scale_id: Mapped[str | None] = mapped_column(String(60))
    operator_name: Mapped[str | None] = mapped_column(String(120))
    measurement_method: Mapped[MeasurementMethod | None] = mapped_column(str_enum(MeasurementMethod, 16))
    challan_ref: Mapped[str | None] = mapped_column(String(60))
    evidence_ref: Mapped[str | None] = mapped_column(String(200))
    assay_evidence_ref: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    material_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_events.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    job: Mapped[JobOrder] = relationship()
    karigar: Mapped[Karigar] = relationship()
    lot: Mapped[MaterialLot] = relationship()
    material_event: Mapped[MaterialEvent] = relationship()
    recorded_by: Mapped[User] = relationship(foreign_keys=[recorded_by_id])


class ReconciliationRun(Base):
    """Immutable versioned snapshot of a fine-gold reconciliation calculation."""

    __tablename__ = "reconciliation_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(nullable=False)
    version_identifier: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ReconciliationStatus] = mapped_column(str_enum(ReconciliationStatus), nullable=False, index=True)

    total_issued_gross_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    total_issued_net_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    total_issued_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    finished_jewellery_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    returned_scrap_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    retained_scrap_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    closing_wip_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    documented_loss_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    expected_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    actual_accounted_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    unexplained_variance_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    variance_pct: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    loss_allowance_pct: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    loss_allowance_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    supporting_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    supporting_return_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    supporting_measurement_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    calculation_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    job: Mapped[JobOrder] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    line_items: Mapped[list["ReconciliationLineItem"]] = relationship(back_populates="reconciliation_run", cascade="all, delete-orphan")


class ReconciliationLineItem(Base):
    """Line item supporting a reconciliation snapshot."""

    __tablename__ = "reconciliation_line_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"))
    lot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_lots.id", ondelete="RESTRICT"))
    gross_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    net_metal_weight_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    fineness_ppt: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    fine_gold_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    reconciliation_run: Mapped[ReconciliationRun] = relationship(back_populates="line_items")
    karigar: Mapped[Karigar | None] = relationship()
    lot: Mapped[MaterialLot | None] = relationship()


class ExceptionCase(Base):
    """Anomalies and workflow discrepancies raised during reconciliation or validation."""

    __tablename__ = "exception_cases"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_exception_code_per_org"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    karigar_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), index=True)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_lots.id", ondelete="RESTRICT"), index=True)

    exception_type: Mapped[ExceptionType] = mapped_column(str_enum(ExceptionType), nullable=False, index=True)
    severity: Mapped[ExceptionSeverity] = mapped_column(str_enum(ExceptionSeverity), nullable=False, index=True)
    status: Mapped[ExceptionStatus] = mapped_column(str_enum(ExceptionStatus), default=ExceptionStatus.open, nullable=False, index=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(String(120))
    observed_value: Mapped[str | None] = mapped_column(String(120))
    variance_amount_g: Mapped[Decimal | None] = mapped_column(Grams)

    supporting_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    supporting_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    assigned_investigator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    investigation_notes: Mapped[str | None] = mapped_column(Text)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolution_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissal_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[JobOrder] = relationship()
    karigar: Mapped[Karigar | None] = relationship()
    lot: Mapped[MaterialLot | None] = relationship()
    assigned_investigator: Mapped[User | None] = relationship(foreign_keys=[assigned_investigator_id])
    evidence_items: Mapped[list["ExceptionEvidence"]] = relationship(back_populates="exception_case", cascade="all, delete-orphan")


class ExceptionEvidence(Base):
    """Evidence records (photos, slips, logs, assay reports) attached to an exception case."""

    __tablename__ = "exception_evidence"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exception_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    exception_case: Mapped[ExceptionCase] = relationship(back_populates="evidence_items")


class InvestigationRun(Base):
    """Persisted run of the AI Investigation Assistant."""

    __tablename__ = "investigation_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exception_cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column()
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    exception_case: Mapped[ExceptionCase] = relationship()
    job: Mapped[JobOrder] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])


class SettlementRule(Base):
    """Versioned commercial terms governing labour rates and wastage allowances."""

    __tablename__ = "settlement_rules"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", "version", name="uq_settlement_rule_code_version"),
        CheckConstraint("labour_rate_per_g >= 0", name="ck_sr_labour_rate_nonneg"),
        CheckConstraint("loss_allowance_pct >= 0 AND loss_allowance_pct <= 10", name="ck_sr_allowance_range"),
        CheckConstraint("gold_rate_per_fine_g >= 0", name="ck_sr_gold_rate_nonneg"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    karat: Mapped[Karat | None] = mapped_column(str_enum(Karat, 8))
    labour_rate_per_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    loss_allowance_pct: Mapped[Decimal] = mapped_column(Fineness, nullable=False)
    gold_rate_per_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = created_at_col()


class SettlementWorksheet(Base):
    """Commercial settlement worksheet calculated from fine-gold reconciliation."""

    __tablename__ = "settlement_worksheets"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code", name="uq_worksheet_code_per_org"),
        CheckConstraint("labour_amount >= 0", name="ck_sw_labour_nonneg"),
        CheckConstraint("gold_recovery_amount >= 0", name="ck_sw_recovery_nonneg"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    karigar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("karigars.id", ondelete="RESTRICT"), nullable=False, index=True)
    settlement_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("settlement_rules.id", ondelete="RESTRICT"))
    reconciliation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="RESTRICT"))

    status: Mapped[SettlementStatus] = mapped_column(str_enum(SettlementStatus), default=SettlementStatus.draft, nullable=False, index=True)

    finished_gross_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    finished_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    labour_rate_applied: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    labour_amount: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    wastage_allowance_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    actual_loss_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    excess_loss_fine_g: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    gold_rate_applied: Mapped[Decimal] = mapped_column(Grams, nullable=False)
    gold_recovery_amount: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    approved_deductions: Mapped[Decimal] = mapped_column(Grams, default=Decimal("0.000"), nullable=False)
    net_payable_amount: Mapped[Decimal] = mapped_column(Grams, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    job: Mapped[JobOrder] = relationship()
    karigar: Mapped[Karigar] = relationship()
    settlement_rule: Mapped[SettlementRule | None] = relationship()
    reconciliation_run: Mapped[ReconciliationRun | None] = relationship()
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])

