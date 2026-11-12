"""Builds response payloads that combine stored rows with ledger-derived state."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import JobOrder, Karigar, MaterialEvent, MaterialEventType, MaterialLot, User
from ..schemas import (
    CustodianOut,
    EventOut,
    EventState,
    JobCustodyLine,
    JobDetail,
    JobHolding,
    JobOut,
    KarigarOut,
    KarigarProfile,
    KarigarRef,
    LotBalance,
    LotOut,
    MeasurementOut,
    Quantity,
    UserRef,
    CustodySummary,
)
from .fine_gold import fine_gold
from .ledger import VAULT, ZERO, followups, job_holdings, job_issued_total, karigar_holding, lot_balances, pending_acknowledgements


def events_out(db: Session, events: list[MaterialEvent]) -> list[EventOut]:
    if not events:
        return []
    fu = followups(db, [e.id for e in events])
    kar_ids = {k for e in events for k in (e.from_karigar_id, e.to_karigar_id) if k}
    karigars = {k.id: k for k in db.scalars(select(Karigar).where(Karigar.id.in_(kar_ids)))} if kar_ids else {}
    lots = {lot.id: lot for lot in db.scalars(select(MaterialLot).where(MaterialLot.id.in_({e.lot_id for e in events})))}
    job_ids = {e.job_id for e in events if e.job_id}
    jobs = {j.id: j for j in db.scalars(select(JobOrder).where(JobOrder.id.in_(job_ids)))} if job_ids else {}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({e.recorded_by_id for e in events})))}

    def cust(ctype, kid) -> CustodianOut:
        k = karigars.get(kid) if kid else None
        return CustodianOut(type=ctype, karigar_id=kid, karigar_code=k.code if k else None, karigar_name=k.name if k else None)

    out = []
    for e in events:
        f = fu[e.id]
        is_issue = e.event_type == MaterialEventType.issue
        out.append(
            EventOut(
                id=e.id,
                event_type=e.event_type,
                lot_id=e.lot_id,
                lot_code=lots[e.lot_id].code,
                job_id=e.job_id,
                job_code=jobs[e.job_id].code if e.job_id in jobs else None,
                **{"from": cust(e.from_type, e.from_karigar_id)},
                to=cust(e.to_type, e.to_karigar_id),
                gross_weight_g=e.gross_weight_g,
                net_weight_g=e.net_weight_g,
                fineness_ppt=e.fineness_ppt,
                fine_gold_g=e.fine_gold_g,
                measurement=MeasurementOut(scale_id=e.scale_id, operator_name=e.operator_name, method=e.measurement_method) if e.scale_id or e.operator_name else None,
                challan_ref=e.challan_ref,
                evidence_ref=e.evidence_ref,
                note=e.note,
                ref_event_id=e.ref_event_id,
                acknowledged_by_name=e.acknowledged_by_name,
                occurred_at=e.occurred_at,
                recorded_at=e.recorded_at,
                recorded_by=UserRef(id=users[e.recorded_by_id].id, full_name=users[e.recorded_by_id].full_name),
                state=EventState(
                    reversed=f.reversal_id is not None,
                    reversal_event_id=f.reversal_id,
                    acknowledged=(f.acknowledgement_id is not None and not f.acknowledgement_reversed) if is_issue else None,
                    acknowledgement_event_id=f.acknowledgement_id if is_issue else None,
                ),
            )
        )
    return out


def _qty(gross, net, fine) -> Quantity:
    return Quantity(gross_weight_g=gross, net_weight_g=net, fine_gold_g=fine)


def lot_out(db: Session, lot: MaterialLot) -> LotOut:
    bal = lot_balances(db, lot)
    vault = bal.get(VAULT)
    others = [q for k, q in bal.items() if k != VAULT]
    k_gross = sum((q.gross for q in others), ZERO)
    k_net = sum((q.net for q in others), ZERO)
    v_gross = vault.gross if vault else ZERO
    v_net = vault.net if vault else ZERO
    base = LotOut.model_validate(lot)
    base.balance = LotBalance(
        vault=_qty(v_gross, v_net, fine_gold(v_net, lot.fineness_ppt)),
        with_karigars=_qty(k_gross, k_net, fine_gold(k_net, lot.fineness_ppt)),
    )
    return base


def karigar_profile(db: Session, k: Karigar) -> KarigarProfile:
    h = karigar_holding(db, k.organisation_id, k.id)
    jobs = {j.id: j for j in db.scalars(select(JobOrder).where(JobOrder.id.in_([j for j in h.by_job if j])))} if h.by_job else {}
    issues = list(db.scalars(select(MaterialEvent).where(MaterialEvent.to_karigar_id == k.id, MaterialEvent.event_type == MaterialEventType.issue)))
    recent = list(
        db.scalars(
            select(MaterialEvent)
            .where((MaterialEvent.to_karigar_id == k.id) | (MaterialEvent.from_karigar_id == k.id))
            .order_by(MaterialEvent.recorded_at.desc())
            .limit(20)
        )
    )
    team = list(db.scalars(select(Karigar).where(Karigar.head_karigar_id == k.id).order_by(Karigar.code)))
    head = db.get(Karigar, k.head_karigar_id) if k.head_karigar_id else None
    return KarigarProfile(
        **KarigarOut.model_validate(k).model_dump(),
        head_karigar=KarigarRef.model_validate(head) if head else None,
        team=[KarigarRef.model_validate(t) for t in team],
        custody=CustodySummary(
            fine_gold_g=h.fine,
            net_weight_g=h.net,
            gross_weight_g=h.gross,
            pending_acknowledgements=pending_acknowledgements(db, issues),
            by_job=[JobHolding(job_id=j, job_code=jobs[j].code if j in jobs else None, net_weight_g=v[0], fine_gold_g=v[1]) for j, v in h.by_job.items() if v[0] != 0],
        ),
        recent_events=events_out(db, recent),
    )


def job_detail(db: Session, job: JobOrder) -> JobDetail:
    issued = job_issued_total(db, job.id)
    holdings = job_holdings(db, job.id)
    karigars = {k.id: k for k in db.scalars(select(Karigar).where(Karigar.id.in_(list(holdings))))} if holdings else {}
    events = list(db.scalars(select(MaterialEvent).where(MaterialEvent.job_id == job.id).order_by(MaterialEvent.recorded_at)))
    return JobDetail(
        **JobOut.model_validate(job).model_dump(),
        issued=_qty(issued.gross, issued.net, issued.fine),
        pending_acknowledgements=pending_acknowledgements(db, events),
        custody=[
            JobCustodyLine(karigar_id=kid, karigar_code=karigars[kid].code, karigar_name=karigars[kid].name, fine_gold_g=h.fine, net_weight_g=h.net)
            for kid, h in holdings.items()
            if h.net != 0
        ],
        events=events_out(db, events),
    )


__all__ = ["events_out", "lot_out", "karigar_profile", "job_detail", "uuid"]
