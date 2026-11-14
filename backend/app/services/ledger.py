"""Custody ledger: derives every balance from append-only MaterialEvent rows.

Rules
  * Only movement events (lot_received, issue, reversal) carry quantities.
  * A reversal mirrors the movement it corrects (from/to swapped, same quantities), so
    summing ALL movement rows gives the corrected balance — nothing is filtered or edited.
  * Balances are tracked in gross and net metal per lot; fine gold is computed from the
    net balance with the lot's fineness (avoids rounding drift from many partial issues).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import MOVEMENT_EVENTS, CustodianType, MaterialEvent, MaterialEventType, MaterialLot
from .fine_gold import GRAM, fine_gold

ZERO = Decimal("0.000")
VAULT = "vault"


@dataclass
class Qty:
    gross: Decimal = ZERO
    net: Decimal = ZERO

    def add(self, gross: Decimal, net: Decimal, sign: int) -> None:
        self.gross = (self.gross + sign * gross).quantize(GRAM)
        self.net = (self.net + sign * net).quantize(GRAM)


@dataclass
class Holding:
    """Net/gross held, with fine gold derived per lot and summed."""

    gross: Decimal = ZERO
    net: Decimal = ZERO
    fine: Decimal = ZERO
    by_job: dict[uuid.UUID | None, list[Decimal]] = field(default_factory=dict)  # job → [net, fine]


def custodian_key(ctype: CustodianType | None, karigar_id: uuid.UUID | None) -> str | None:
    if ctype == CustodianType.vault:
        return VAULT
    if ctype == CustodianType.karigar and karigar_id:
        return str(karigar_id)
    return None  # external / none: outside the system's custody


def _movements(db: Session, *conditions) -> list[MaterialEvent]:
    stmt = select(MaterialEvent).where(MaterialEvent.event_type.in_([e.value for e in MOVEMENT_EVENTS]), *conditions)
    return list(db.scalars(stmt))


def lot_balances(db: Session, lot: MaterialLot) -> dict[str, Qty]:
    """Per-custodian gross/net held from one lot ('vault' or karigar id string)."""
    out: dict[str, Qty] = defaultdict(Qty)
    for e in _movements(db, MaterialEvent.lot_id == lot.id):
        frm = custodian_key(e.from_type, e.from_karigar_id)
        to = custodian_key(e.to_type, e.to_karigar_id)
        if frm:
            out[frm].add(e.gross_weight_g, e.net_weight_g, -1)
        if to:
            out[to].add(e.gross_weight_g, e.net_weight_g, +1)
    return out


def _fine_for(lot: MaterialLot, net: Decimal) -> Decimal:
    return fine_gold(net, lot.fineness_ppt) if net else ZERO


def karigar_holding(db: Session, organisation_id: uuid.UUID, karigar_id: uuid.UUID) -> Holding:
    events = _movements(
        db,
        MaterialEvent.organisation_id == organisation_id,
        or_(MaterialEvent.to_karigar_id == karigar_id, MaterialEvent.from_karigar_id == karigar_id),
    )
    per_lot_job: dict[tuple[uuid.UUID, uuid.UUID | None], Qty] = defaultdict(Qty)
    for e in events:
        sign = +1 if e.to_karigar_id == karigar_id and e.to_type == CustodianType.karigar else -1
        per_lot_job[(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, sign)
    return _summarise(db, per_lot_job)


def job_holdings(db: Session, job_id: uuid.UUID) -> dict[uuid.UUID, Holding]:
    """Fine gold each karigar holds on a job."""
    per: dict[uuid.UUID, dict[tuple[uuid.UUID, uuid.UUID | None], Qty]] = defaultdict(lambda: defaultdict(Qty))
    for e in _movements(db, MaterialEvent.job_id == job_id):
        if e.to_type == CustodianType.karigar and e.to_karigar_id:
            per[e.to_karigar_id][(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, +1)
        if e.from_type == CustodianType.karigar and e.from_karigar_id:
            per[e.from_karigar_id][(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, -1)
    return {k: _summarise(db, v) for k, v in per.items()}


def job_issued_total(db: Session, job_id: uuid.UUID) -> Holding:
    """Gross/net metal originally issued to karigars for a job (issues minus reversed issues).
    Internal transfers and returns do not affect this total."""
    per_lot: dict[tuple[uuid.UUID, uuid.UUID | None], Qty] = defaultdict(Qty)
    events = _movements(db, MaterialEvent.job_id == job_id)
    issue_ids = {e.id for e in events if e.event_type == MaterialEventType.issue}
    for e in events:
        if e.event_type == MaterialEventType.issue:
            per_lot[(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, +1)
        elif e.event_type == MaterialEventType.reversal and e.ref_event_id in issue_ids:
            per_lot[(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, -1)
    return _summarise(db, per_lot)


def job_returned_total(db: Session, job_id: uuid.UUID) -> Holding:
    """Gross/net metal returned from karigars back to the vault for a job (returns minus reversed returns)."""
    per_lot: dict[tuple[uuid.UUID, uuid.UUID | None], Qty] = defaultdict(Qty)
    events = _movements(db, MaterialEvent.job_id == job_id)
    return_ids = {e.id for e in events if e.event_type == MaterialEventType.return_vault}
    for e in events:
        if e.event_type == MaterialEventType.return_vault:
            per_lot[(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, +1)
        elif e.event_type == MaterialEventType.reversal and e.ref_event_id in return_ids:
            per_lot[(e.lot_id, e.job_id)].add(e.gross_weight_g, e.net_weight_g, -1)
    return _summarise(db, per_lot)


def _summarise(db: Session, per_lot_job: dict[tuple[uuid.UUID, uuid.UUID | None], Qty]) -> Holding:
    h = Holding()
    lots = {lot.id: lot for lot in db.scalars(select(MaterialLot).where(MaterialLot.id.in_({k[0] for k in per_lot_job})))} if per_lot_job else {}
    for (lot_id, job_id), q in per_lot_job.items():
        if q.net == 0 and q.gross == 0:
            continue
        f = _fine_for(lots[lot_id], q.net)
        h.gross += q.gross
        h.net += q.net
        h.fine += f
        acc = h.by_job.setdefault(job_id, [ZERO, ZERO])
        acc[0] += q.net
        acc[1] += f
    h.gross, h.net, h.fine = h.gross.quantize(GRAM), h.net.quantize(GRAM), h.fine.quantize(GRAM)
    return h


# --------------------------------------------------------------- follow-ups


@dataclass
class FollowUps:
    reversal_id: uuid.UUID | None = None
    acknowledgement_id: uuid.UUID | None = None
    acknowledgement_reversed: bool = False


def followups(db: Session, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, FollowUps]:
    """For each event: its reversal (if any) and, for issues/transfers, its acknowledgement (and whether revoked)."""
    out: dict[uuid.UUID, FollowUps] = {i: FollowUps() for i in event_ids}
    if not event_ids:
        return out
    children = list(db.scalars(select(MaterialEvent).where(MaterialEvent.ref_event_id.in_(event_ids))))
    ack_types = {MaterialEventType.issue_acknowledged, MaterialEventType.transfer_acknowledged}
    ack_ids = [c.id for c in children if c.event_type in ack_types]
    revoked = {c.ref_event_id for c in db.scalars(select(MaterialEvent).where(MaterialEvent.ref_event_id.in_(ack_ids), MaterialEvent.event_type == MaterialEventType.reversal))} if ack_ids else set()
    for c in children:
        f = out[c.ref_event_id]
        if c.event_type == MaterialEventType.reversal:
            f.reversal_id = c.id
        elif c.event_type in ack_types:
            f.acknowledgement_id = c.id
            f.acknowledgement_reversed = c.id in revoked
    return out


def pending_acknowledgements(db: Session, events: list[MaterialEvent]) -> int:
    ack_needed = [e for e in events if e.event_type in (MaterialEventType.issue, MaterialEventType.transfer)]
    fu = followups(db, [e.id for e in ack_needed])
    return sum(1 for e in ack_needed if fu[e.id].reversal_id is None and (fu[e.id].acknowledgement_id is None or fu[e.id].acknowledgement_reversed))
