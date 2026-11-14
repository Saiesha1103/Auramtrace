"""Status / type enums. Values are stable snake_case API strings shared with the frontend."""

from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"  # organisation + user management, everything below
    manager = "manager"  # karigars, jobs, issuance, acknowledgement, reversals, audit read
    vault_operator = "vault_operator"  # lots, issuance, acknowledgement
    viewer = "viewer"  # read-only


class KarigarKind(StrEnum):
    head_karigar = "head_karigar"
    karigar = "karigar"
    subcontractor = "subcontractor"


class KarigarStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class JobStatus(StrEnum):
    """Full lifecycle shared with the frontend. Phase 1 sets draft / issued / cancelled;
    later phases (transfers, production, returns, reconciliation, settlement) set the rest."""

    draft = "draft"
    issued = "issued"
    in_production = "in_production"
    returned = "returned"
    reconciled = "reconciled"
    settled = "settled"
    cancelled = "cancelled"


class Karat(StrEnum):
    k24 = "24K"
    k22 = "22K"
    k18 = "18K"
    k14 = "14K"


class MetalType(StrEnum):
    gold = "gold"


class MeasurementMethod(StrEnum):
    manual = "manual"  # typed in by an operator
    imported = "imported"  # from another system / file
    device = "device"  # captured from an integrated scale (none integrated in Phase 1)


class CustodianType(StrEnum):
    external = "external"  # supplier / refinery outside the system
    vault = "vault"
    karigar = "karigar"


class MaterialEventType(StrEnum):
    """Event types for append-only custody ledger.
    Storage is a plain string column, no DB enum to migrate."""

    lot_received = "lot_received"  # metal enters the vault (creates custody)
    issue = "issue"  # vault → karigar
    issue_acknowledged = "issue_acknowledged"  # receiver signs for an issue
    transfer = "transfer"  # karigar → karigar
    transfer_acknowledged = "transfer_acknowledged"  # receiving karigar signs for transfer
    return_vault = "return_vault"  # karigar → vault (finished jewellery, scrap, dust, WIP)
    reversal = "reversal"  # correction: mirrors a previous event; original stays untouched


#: event types that move metal (carry quantities and from/to custodians)
MOVEMENT_EVENTS = {
    MaterialEventType.lot_received,
    MaterialEventType.issue,
    MaterialEventType.transfer,
    MaterialEventType.return_vault,
    MaterialEventType.reversal,
}


class ReturnCategory(StrEnum):
    finished_jewellery = "finished_jewellery"
    scrap = "scrap"
    dust = "dust"
    wip = "wip"


class ProductionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    paused = "paused"


class ReconciliationStatus(StrEnum):
    within_allowance = "within_allowance"
    above_allowance = "above_allowance"
    missing_measurement = "missing_measurement"
    missing_return = "missing_return"
    fineness_mismatch = "fineness_mismatch"
    weight_inconsistency = "weight_inconsistency"
    unacknowledged_transfer = "unacknowledged_transfer"
    unexplained_material_variance = "unexplained_material_variance"
    pending_reconciliation = "pending_reconciliation"


class ExceptionSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ExceptionStatus(StrEnum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    dismissed = "dismissed"


class ExceptionType(StrEnum):
    variance = "variance"
    purity_mismatch = "purity_mismatch"
    unacknowledged_transfer = "unacknowledged_transfer"
    unacknowledged_issue = "unacknowledged_issue"
    weight_discrepancy = "weight_discrepancy"
    missing_measurement = "missing_measurement"
    unexpected_loss = "unexpected_loss"
    custody_mismatch = "custody_mismatch"
    overdue_job = "overdue_job"
    outstanding_wip = "outstanding_wip"


class SettlementStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"

