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
    """Phase 1 event types. Niharika's phase adds transfer / transfer_acknowledged / return /
    production_* etc. — add values here; storage is a plain string column, no DB enum to migrate."""

    lot_received = "lot_received"  # metal enters the vault (creates custody)
    issue = "issue"  # vault → karigar
    issue_acknowledged = "issue_acknowledged"  # receiver signs for an issue (no quantity)
    reversal = "reversal"  # correction: mirrors a previous event; the original stays untouched


#: event types that move metal (carry quantities and from/to custodians)
MOVEMENT_EVENTS = {MaterialEventType.lot_received, MaterialEventType.issue, MaterialEventType.reversal}
