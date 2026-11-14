"""Production and manufacturing process tracking service.

Handles:
  * Multi-stage production workflows (Melting, Casting, Rolling, Setting, Polishing, QC, etc.)
  * Physical measurements: input/output gross/net, stone weight, alloy additions
  * Audited superseding measurements (original records are never mutated)
  * Production timelines and stage progression
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import BusinessRuleViolation, NotFound
from ..models import (
    JobOrder,
    JobStatus,
    Karigar,
    ProductionEntry,
    ProductionMeasurement,
    ProductionStatus,
    User,
)
from ..models.base import utcnow
from ..schemas import (
    ProductionEntryCreate,
    ProductionEntryOut,
    ProductionEntryUpdate,
    ProductionMeasurementCreate,
    ProductionMeasurementOut,
)
from . import audit
from .custody import get_in_org


def create_production_entry(db: Session, user: User, req: ProductionEntryCreate) -> ProductionEntry:
    org = user.organisation_id
    job = get_in_org(db, JobOrder, org, req.job_id, "Job")
    karigar = get_in_org(db, Karigar, org, req.karigar_id, "Karigar")

    if job.status == JobStatus.cancelled:
        raise BusinessRuleViolation("Cannot track production for a cancelled job", code="job_cancelled")

    entry = ProductionEntry(
        organisation_id=org,
        job_id=job.id,
        karigar_id=karigar.id,
        stage=req.stage,
        status=req.status,
        started_at=req.started_at or utcnow(),
        note=req.note,
        created_by_id=user.id,
    )
    db.add(entry)

    if job.status in (JobStatus.draft, JobStatus.issued):
        job.status = JobStatus.in_production

    db.flush()
    audit.record(
        db,
        user,
        org,
        "production.entry_created",
        "production_entry",
        entry.id,
        {"jobCode": job.code, "karigarCode": karigar.code, "stage": req.stage, "status": req.status.value},
    )
    return entry


def update_production_entry(db: Session, user: User, entry: ProductionEntry, req: ProductionEntryUpdate) -> ProductionEntry:
    if req.note is not None:
        entry.note = req.note
    if req.status is not None:
        entry.status = req.status
        if req.status == ProductionStatus.completed and entry.completed_at is None:
            entry.completed_at = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        entry.organisation_id,
        "production.entry_updated",
        "production_entry",
        entry.id,
        {"status": entry.status.value, "hasNote": bool(entry.note)},
    )
    return entry


def complete_production_entry(db: Session, user: User, entry: ProductionEntry) -> ProductionEntry:
    entry.status = ProductionStatus.completed
    entry.completed_at = utcnow()
    db.flush()
    audit.record(
        db,
        user,
        entry.organisation_id,
        "production.entry_completed",
        "production_entry",
        entry.id,
        {"completedAt": entry.completed_at.isoformat()},
    )
    return entry


def create_production_measurement(db: Session, user: User, req: ProductionMeasurementCreate) -> ProductionMeasurement:
    org = user.organisation_id
    job = get_in_org(db, JobOrder, org, req.job_id, "Job")
    karigar = get_in_org(db, Karigar, org, req.karigar_id, "Karigar")

    if req.production_entry_id:
        get_in_org(db, ProductionEntry, org, req.production_entry_id, "Production entry")

    # If this measurement supersedes an earlier one, validate and link it
    superseded_meas = None
    if req.supersedes_id:
        superseded_meas = get_in_org(db, ProductionMeasurement, org, req.supersedes_id, "Original measurement")
        if not req.correction_reason:
            raise BusinessRuleViolation("A correction reason is required when superseding a measurement", code="missing_correction_reason")

    measurement = ProductionMeasurement(
        organisation_id=org,
        production_entry_id=req.production_entry_id,
        job_id=job.id,
        karigar_id=karigar.id,
        stage=req.stage,
        input_gross_weight_g=req.input_gross_weight_g,
        input_net_metal_weight_g=req.input_net_metal_weight_g,
        output_gross_weight_g=req.output_gross_weight_g,
        output_net_metal_weight_g=req.output_net_metal_weight_g,
        stone_weight_g=req.stone_weight_g,
        alloy_weight_g=req.alloy_weight_g,
        fineness_ppt=req.fineness_ppt,
        pieces=req.pieces,
        scale_id=req.scale_id,
        operator_name=req.operator_name,
        measurement_method=req.measurement_method,
        evidence_ref=req.evidence_ref,
        notes=req.notes,
        is_superseded=False,
        recorded_at=utcnow(),
        recorded_by_id=user.id,
    )
    db.add(measurement)
    db.flush()

    if superseded_meas:
        superseded_meas.is_superseded = True
        superseded_meas.superseded_by_id = measurement.id
        superseded_meas.correction_reason = req.correction_reason
        db.flush()

    audit.record(
        db,
        user,
        org,
        "production.measurement_recorded",
        "production_measurement",
        measurement.id,
        {
            "jobCode": job.code,
            "karigarCode": karigar.code,
            "stage": req.stage,
            "inputNetWeightG": req.input_net_metal_weight_g,
            "outputNetWeightG": req.output_net_metal_weight_g,
            "isCorrection": bool(superseded_meas),
        },
    )
    return measurement


def list_production_entries(db: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, karigar_id: uuid.UUID | None = None) -> list[ProductionEntry]:
    stmt = select(ProductionEntry).where(ProductionEntry.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(ProductionEntry.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(ProductionEntry.karigar_id == karigar_id)
    return list(db.scalars(stmt.order_by(ProductionEntry.started_at.desc())))


def list_production_measurements(db: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, karigar_id: uuid.UUID | None = None) -> list[ProductionMeasurement]:
    stmt = select(ProductionMeasurement).where(ProductionMeasurement.organisation_id == org_id)
    if job_id:
        stmt = stmt.where(ProductionMeasurement.job_id == job_id)
    if karigar_id:
        stmt = stmt.where(ProductionMeasurement.karigar_id == karigar_id)
    return list(db.scalars(stmt.order_by(ProductionMeasurement.recorded_at.desc())))
