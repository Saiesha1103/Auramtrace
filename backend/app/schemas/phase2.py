"""Pydantic schemas for Phase 2: Transfers, Production, Returns, Reconciliation, Exceptions, AI, Settlement."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_validator

from ..models.enums import (
    CustodianType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    JobStatus,
    Karat,
    KarigarKind,
    MeasurementMethod,
    ProductionStatus,
    ReconciliationStatus,
    ReturnCategory,
    SettlementStatus,
)
from .common import CamelModel, Fineness, Grams, MeasurementIn, MeasurementOut, UtcDateTime
from .core import KarigarRef
from typing import Annotated
from pydantic import PlainSerializer

Percent = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


# ----------------------------------------------------------------- transfers


class TransferCreate(CamelModel):
    job_id: uuid.UUID
    from_karigar_id: uuid.UUID
    to_karigar_id: uuid.UUID
    lot_id: uuid.UUID
    gross_weight_g: Grams
    net_weight_g: Grams
    measurement: MeasurementIn
    challan_ref: str | None = Field(default=None, max_length=60)
    evidence_ref: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_custody(self) -> "TransferCreate":
        if self.from_karigar_id == self.to_karigar_id:
            raise ValueError("Sender and receiver karigar cannot be the same")
        if self.net_weight_g > self.gross_weight_g:
            raise ValueError("Net metal weight cannot exceed gross weight")
        return self


class TransferAcknowledgeRequest(CamelModel):
    acknowledged_by_name: str = Field(min_length=2, max_length=120)
    evidence_ref: str | None = Field(default=None, max_length=200)
    note: str | None = None
    occurred_at: datetime | None = None


class TransferReverseRequest(CamelModel):
    reason: str = Field(min_length=4, max_length=500)


class TransferOut(CamelModel):
    id: uuid.UUID
    event_id: uuid.UUID
    job_id: uuid.UUID
    lot_id: uuid.UUID
    from_karigar: KarigarRef
    to_karigar: KarigarRef
    gross_weight_g: Grams
    net_weight_g: Grams
    fineness_ppt: Fineness
    fine_gold_g: Grams
    measurement: MeasurementOut
    challan_ref: str | None
    evidence_ref: str | None
    note: str | None
    is_acknowledged: bool
    acknowledged_by_name: str | None
    acknowledged_at: UtcDateTime | None
    is_reversed: bool
    occurred_at: UtcDateTime
    recorded_at: UtcDateTime


# ----------------------------------------------------------------- job splitting & lineage


class JobSplitRequest(CamelModel):
    allocated_pieces: int = Field(gt=0, description="Pieces carved out for child job")
    allocated_gross_weight_g: Grams | None = None
    split_reason: str | None = Field(default=None, max_length=200)
    child_job_code: str | None = Field(default=None, max_length=24)
    child_title: str | None = Field(default=None, max_length=200)
    head_karigar_id: uuid.UUID | None = None
    due_date: date | None = None


class JobRef(CamelModel):
    id: uuid.UUID
    code: str
    title: str
    status: JobStatus


class JobSplitOut(CamelModel):
    id: uuid.UUID
    parent_job_id: uuid.UUID
    child_job_id: uuid.UUID
    allocated_pieces: int
    allocated_gross_weight_g: Grams | None
    split_reason: str | None
    created_at: UtcDateTime


class JobLineageOut(CamelModel):
    job_id: uuid.UUID
    code: str
    title: str
    parent_job: JobRef | None
    child_jobs: list[JobRef]
    splits: list[JobSplitOut]
    total_events: int


class CustodyLineageNode(CamelModel):
    custodian_type: CustodianType
    karigar_id: uuid.UUID | None
    name: str
    kind: str | None
    net_weight_g: Grams
    fine_gold_g: Grams


class CustodyLineageEdge(CamelModel):
    source: str
    target: str
    event_id: uuid.UUID
    event_type: str
    gross_weight_g: Grams
    net_weight_g: Grams
    fine_gold_g: Grams
    recorded_at: UtcDateTime


class CustodyLineageGraph(CamelModel):
    job_id: uuid.UUID
    nodes: list[CustodyLineageNode]
    edges: list[CustodyLineageEdge]


# ----------------------------------------------------------------- production


class ProductionEntryCreate(CamelModel):
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    stage: str = Field(min_length=2, max_length=60)
    status: ProductionStatus = ProductionStatus.in_progress
    started_at: datetime | None = None
    note: str | None = None


class ProductionEntryUpdate(CamelModel):
    note: str | None = Field(default=None, max_length=1000)
    status: ProductionStatus | None = None


class ProductionEntryOut(CamelModel):
    id: uuid.UUID
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    karigar_name: str
    stage: str
    status: ProductionStatus
    started_at: UtcDateTime
    completed_at: UtcDateTime | None
    note: str | None
    measurements_count: int
    created_at: UtcDateTime


class ProductionMeasurementCreate(CamelModel):
    production_entry_id: uuid.UUID | None = None
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    stage: str = Field(min_length=2, max_length=60)
    input_gross_weight_g: Grams
    input_net_metal_weight_g: Grams
    output_gross_weight_g: Grams
    output_net_metal_weight_g: Grams
    stone_weight_g: Grams = Decimal("0.000")
    alloy_weight_g: Grams = Decimal("0.000")
    fineness_ppt: Fineness
    pieces: int = Field(default=1, gt=0)
    scale_id: str | None = Field(default=None, max_length=60)
    operator_name: str | None = Field(default=None, max_length=120)
    measurement_method: MeasurementMethod = MeasurementMethod.manual
    evidence_ref: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    supersedes_id: uuid.UUID | None = None
    correction_reason: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def _validate_weights(self) -> "ProductionMeasurementCreate":
        if self.input_net_metal_weight_g > self.input_gross_weight_g:
            raise ValueError("Input net metal weight cannot exceed input gross weight")
        if self.output_net_metal_weight_g > self.output_gross_weight_g:
            raise ValueError("Output net metal weight cannot exceed output gross weight")
        return self


class ProductionMeasurementOut(CamelModel):
    id: uuid.UUID
    production_entry_id: uuid.UUID | None
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    stage: str
    input_gross_weight_g: Grams
    input_net_metal_weight_g: Grams
    output_gross_weight_g: Grams
    output_net_metal_weight_g: Grams
    stone_weight_g: Grams
    alloy_weight_g: Grams
    fineness_ppt: Fineness
    pieces: int
    scale_id: str | None
    operator_name: str | None
    measurement_method: MeasurementMethod | None
    evidence_ref: str | None
    notes: str | None
    is_superseded: bool
    superseded_by_id: uuid.UUID | None
    correction_reason: str | None
    recorded_at: UtcDateTime
    created_at: UtcDateTime


# ----------------------------------------------------------------- returns


class MaterialReturnCreate(CamelModel):
    code: str | None = Field(default=None, max_length=24, description="Optional RET-0001 code")
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    lot_id: uuid.UUID
    return_category: ReturnCategory
    gross_weight_g: Grams
    net_metal_weight_g: Grams
    stone_weight_g: Grams = Decimal("0.000")
    declared_fineness_ppt: Fineness
    assayed_fineness_ppt: Fineness | None = None
    pieces: int = Field(default=1, gt=0)
    is_partial: bool = False
    retained_scrap_g: Grams = Decimal("0.000")
    measurement: MeasurementIn
    challan_ref: str | None = Field(default=None, max_length=60)
    evidence_ref: str | None = Field(default=None, max_length=200)
    assay_evidence_ref: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_return(self) -> "MaterialReturnCreate":
        if self.net_metal_weight_g > self.gross_weight_g:
            raise ValueError("Net metal weight cannot exceed gross weight")
        return self


class MaterialReturnAssayUpdate(CamelModel):
    assayed_fineness_ppt: Fineness
    assay_evidence_ref: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class MaterialReturnOut(CamelModel):
    id: uuid.UUID
    code: str
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    lot_id: uuid.UUID
    return_category: ReturnCategory
    gross_weight_g: Grams
    net_metal_weight_g: Grams
    stone_weight_g: Grams
    declared_fineness_ppt: Fineness
    assayed_fineness_ppt: Fineness | None
    fine_gold_g: Grams
    pieces: int
    is_partial: bool
    retained_scrap_g: Grams
    scale_id: str | None
    operator_name: str | None
    measurement_method: MeasurementMethod | None
    challan_ref: str | None
    evidence_ref: str | None
    assay_evidence_ref: str | None
    notes: str | None
    material_event_id: uuid.UUID
    created_at: UtcDateTime


# ----------------------------------------------------------------- reconciliation


class ReconciliationLineItemOut(CamelModel):
    id: uuid.UUID
    category: str
    karigar_id: uuid.UUID | None
    lot_id: uuid.UUID | None
    gross_weight_g: Grams
    net_metal_weight_g: Grams
    fineness_ppt: Fineness
    fine_gold_g: Grams
    notes: str | None


class ReconciliationRunOut(CamelModel):
    id: uuid.UUID
    job_id: uuid.UUID
    run_number: int
    version_identifier: str
    status: ReconciliationStatus
    total_issued_gross_g: Grams
    total_issued_net_g: Grams
    total_issued_fine_g: Grams
    finished_jewellery_fine_g: Grams
    returned_scrap_fine_g: Grams
    retained_scrap_fine_g: Grams
    closing_wip_fine_g: Grams
    documented_loss_fine_g: Grams
    expected_fine_g: Grams
    actual_accounted_fine_g: Grams
    unexplained_variance_fine_g: Grams
    variance_pct: Percent
    loss_allowance_pct: Percent
    loss_allowance_fine_g: Grams
    supporting_event_ids: list[str]
    supporting_return_ids: list[str]
    supporting_measurement_ids: list[str]
    calculation_details: dict[str, Any]
    is_latest: bool
    created_at: UtcDateTime
    line_items: list[ReconciliationLineItemOut] = []


class ReconciliationSummaryOut(CamelModel):
    total_jobs: int
    reconciled_jobs: int
    jobs_with_exceptions: int
    open_wip_jobs: int
    total_issued_fine_g: Grams
    total_accounted_fine_g: Grams
    total_variance_fine_g: Grams


# ----------------------------------------------------------------- exceptions


class ExceptionCaseOut(CamelModel):
    id: uuid.UUID
    code: str
    job_id: uuid.UUID
    karigar_id: uuid.UUID | None
    lot_id: uuid.UUID | None
    exception_type: ExceptionType
    severity: ExceptionSeverity
    status: ExceptionStatus
    description: str
    expected_value: str | None
    observed_value: str | None
    variance_amount_g: Grams | None
    supporting_event_ids: list[str]
    supporting_record_ids: list[str]
    assigned_investigator_id: uuid.UUID | None
    investigation_notes: str | None
    resolution_notes: str | None
    resolution_timestamp: UtcDateTime | None
    dismissal_reason: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ExceptionAssignRequest(CamelModel):
    investigator_id: uuid.UUID


class ExceptionStatusUpdateRequest(CamelModel):
    status: ExceptionStatus
    notes: str | None = None


class ExceptionNotesRequest(CamelModel):
    notes: str = Field(min_length=2, max_length=2000)


class ExceptionResolveRequest(CamelModel):
    resolution_notes: str = Field(min_length=4, max_length=2000)


class ExceptionDismissRequest(CamelModel):
    reason: str = Field(min_length=4, max_length=1000, description="Mandatory reason for dismissal")


class ExceptionEvidenceOut(CamelModel):
    id: uuid.UUID
    exception_id: uuid.UUID
    evidence_type: str
    title: str
    file_url: str | None
    details: dict[str, Any]
    created_at: UtcDateTime


# ----------------------------------------------------------------- AI investigation


class InvestigationRunRequest(CamelModel):
    exception_id: uuid.UUID


class InvestigationRunOut(CamelModel):
    id: uuid.UUID
    exception_id: uuid.UUID
    job_id: uuid.UUID
    provider: str
    response: dict[str, Any]
    confidence: float | None
    created_at: UtcDateTime


# ----------------------------------------------------------------- settlement


class SettlementRuleCreate(CamelModel):
    code: str | None = Field(default=None, max_length=24)
    name: str = Field(min_length=2, max_length=160)
    karat: Karat | None = None
    labour_rate_per_g: Grams = Field(description="Labour rate in INR per gram of finished jewellery")
    loss_allowance_pct: Percent = Field(description="Contractual wastage allowance percentage")
    gold_rate_per_fine_g: Grams = Field(description="Gold rate in INR per fine gram for excess loss recovery")
    effective_from: date
    effective_to: date | None = None


class SettlementRuleOut(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    karat: Karat | None
    labour_rate_per_g: Grams
    loss_allowance_pct: Percent
    gold_rate_per_fine_g: Grams
    effective_from: date
    effective_to: date | None
    is_active: bool
    version: int
    created_at: UtcDateTime


class SettlementWorksheetCreate(CamelModel):
    job_id: uuid.UUID
    karigar_id: uuid.UUID | None = None
    settlement_rule_id: uuid.UUID | None = None
    approved_deductions: Grams = Decimal("0.000")
    notes: str | None = None


class SettlementWorksheetOut(CamelModel):
    id: uuid.UUID
    code: str
    job_id: uuid.UUID
    karigar_id: uuid.UUID
    settlement_rule_id: uuid.UUID | None
    reconciliation_run_id: uuid.UUID | None
    status: SettlementStatus
    finished_gross_g: Grams
    finished_fine_g: Grams
    labour_rate_applied: Grams
    labour_amount: Grams
    wastage_allowance_fine_g: Grams
    actual_loss_fine_g: Grams
    excess_loss_fine_g: Grams
    gold_rate_applied: Grams
    gold_recovery_amount: Grams
    approved_deductions: Grams
    net_payable_amount: Grams
    notes: str | None
    rejection_reason: str | None
    submitted_at: UtcDateTime | None
    approved_at: UtcDateTime | None
    created_at: UtcDateTime


class SettlementApproveRequest(CamelModel):
    notes: str | None = None


class SettlementRejectRequest(CamelModel):
    reason: str = Field(min_length=4, max_length=1000)
