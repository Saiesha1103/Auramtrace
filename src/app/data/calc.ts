import { AS_OF, VAULT } from './seed';
import type { Job, JobStatus, ReturnEntry, ReturnType } from './types';
import type { AppState } from './store';

/**
 * Pure, deterministic calculations. Same state in → same numbers out.
 * Fine gold is always gross × fineness, rounded to 0.001 g (milligram).
 */

export const r3 = (n: number) => Math.round(n * 1000) / 1000;
export const fine = (gross: number, fineness: number) => r3(gross * fineness);
export const returnFine = (r: ReturnEntry) => fine(r.gross, r.assayedFineness ?? r.declaredFineness);

/** Synthetic reference rate used only to value gold differences in settlement (₹ per fine gram). */
export const GOLD_RATE_PER_FINE_G = 7850;

export function daysBetween(a: string, b: string) {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}

/* ------------------------------------------------------------------ ledger */

export type LedgerKind = 'Issue' | 'Transfer' | 'Return';
export interface LedgerEvent {
  id: string;
  date: string;
  jobId: string;
  kind: LedgerKind;
  detail: string;
  from: string;
  to: string;
  gross: number;
  fineness: number;
  fine: number;
}

export function ledger(s: AppState): LedgerEvent[] {
  const ev: LedgerEvent[] = [];
  for (const l of s.lots)
    ev.push({ id: l.id, date: l.date, jobId: l.jobId, kind: 'Issue', detail: l.source, from: VAULT, to: l.issuedTo, gross: l.gross, fineness: l.fineness, fine: fine(l.gross, l.fineness) });
  for (const t of s.transfers)
    ev.push({ id: t.id, date: t.date, jobId: t.jobId, kind: 'Transfer', detail: `${t.kind} · ${t.purpose}`, from: t.from, to: t.to, gross: t.gross, fineness: t.fineness, fine: fine(t.gross, t.fineness) });
  for (const r of s.returns)
    ev.push({ id: r.id, date: r.date, jobId: r.jobId, kind: 'Return', detail: `${r.type}${r.partial ? ' · partial' : ''}`, from: r.from, to: VAULT, gross: r.gross, fineness: r.assayedFineness ?? r.declaredFineness, fine: returnFine(r) });
  return ev.sort((a, b) => (a.date === b.date ? a.id.localeCompare(b.id) : a.date.localeCompare(b.date)));
}

/** Fine gold held per party, optionally restricted to one job. Vault is excluded. */
export function custody(s: AppState, jobId?: string): Map<string, number> {
  const m = new Map<string, number>();
  const add = (id: string, v: number) => id !== VAULT && m.set(id, r3((m.get(id) ?? 0) + v));
  for (const e of ledger(s)) {
    if (jobId && e.jobId !== jobId) continue;
    add(e.to, e.fine);
    add(e.from, -e.fine);
  }
  return m;
}

/* ---------------------------------------------------------- reconciliation */

export type ReconStatus = 'Not issued' | 'Open' | 'Within tolerance' | 'Exception';

export interface JobRecon {
  jobId: string;
  issuedFine: number;
  returnedFine: number;
  returnedByType: Record<ReturnType, number>;
  outstandingFine: number;
  closed: boolean;
  allowanceFine: number;
  varianceFine: number;
  unexplainedFine: number;
  /** fine gold lost to purity shortfalls found at assay (declared − assayed) */
  purityShortfallFine: number;
  status: ReconStatus;
}

export function reconcile(s: AppState, job: Job): JobRecon {
  const lots = s.lots.filter((l) => l.jobId === job.id);
  const rets = s.returns.filter((r) => r.jobId === job.id);
  const issuedFine = r3(lots.reduce((a, l) => a + fine(l.gross, l.fineness), 0));
  const returnedByType: Record<ReturnType, number> = { 'Finished goods': 0, Scrap: 0, 'Dust & sweep': 0, WIP: 0 };
  for (const r of rets) returnedByType[r.type] = r3(returnedByType[r.type] + returnFine(r));
  const returnedFine = r3(rets.reduce((a, r) => a + returnFine(r), 0));
  const outstandingFine = r3(issuedFine - returnedFine);
  const closed = rets.some((r) => !r.partial);
  const allowanceFine = r3((issuedFine * job.lossAllowancePct) / 100);
  const varianceFine = closed ? outstandingFine : 0;
  const unexplainedFine = closed ? r3(Math.max(0, varianceFine - allowanceFine)) : 0;
  const purityShortfallFine = r3(
    rets.reduce((a, r) => a + (r.assayedFineness !== undefined && r.assayedFineness < r.declaredFineness ? r.gross * (r.declaredFineness - r.assayedFineness) : 0), 0),
  );
  const status: ReconStatus = lots.length === 0 ? 'Not issued' : !closed ? 'Open' : unexplainedFine > 0 ? 'Exception' : 'Within tolerance';
  return { jobId: job.id, issuedFine, returnedFine, returnedByType, outstandingFine, closed, allowanceFine, varianceFine, unexplainedFine, purityShortfallFine, status };
}

/* --------------------------------------------------------------- job state */

export function jobStatus(s: AppState, job: Job): JobStatus {
  const rec = reconcile(s, job);
  if (s.settlement[job.id] === 'Approved') return 'Settled';
  if (rec.status === 'Not issued') return 'Draft';
  if (rec.closed) return rec.status === 'Within tolerance' ? 'Reconciled' : 'Returned';
  const started = s.transfers.some((t) => t.jobId === job.id) || s.production.some((p) => p.jobId === job.id);
  return started ? 'In production' : 'Issued';
}

export function isOverdue(s: AppState, job: Job) {
  const st = jobStatus(s, job);
  return job.deadline < AS_OF && (st === 'In production' || st === 'Issued' || st === 'Draft');
}

/* --------------------------------------------------------------- exceptions */

export type ExceptionKind = 'Variance' | 'Purity mismatch' | 'Unacknowledged lot' | 'Overdue job';
export interface ExceptionItem {
  id: string;
  jobId: string;
  kind: ExceptionKind;
  severity: 'High' | 'Medium' | 'Low';
  amountFine: number | null;
  summary: string;
  raised: string;
}

export function exceptions(s: AppState): ExceptionItem[] {
  const out: ExceptionItem[] = [];
  for (const job of s.jobs) {
    const n = job.id.slice(2);
    const rec = reconcile(s, job);
    if (rec.status === 'Exception') {
      const lastReturn = s.returns.filter((r) => r.jobId === job.id).map((r) => r.date).sort().pop() ?? AS_OF;
      out.push({
        id: `EX-${n}-V`,
        jobId: job.id,
        kind: 'Variance',
        severity: rec.unexplainedFine >= 0.1 ? 'High' : 'Medium',
        amountFine: rec.unexplainedFine,
        summary: `${rec.unexplainedFine.toFixed(3)} g fine beyond the ${job.lossAllowancePct}% loss allowance`,
        raised: lastReturn,
      });
    }
    for (const r of s.returns.filter((x) => x.jobId === job.id && x.assayedFineness !== undefined && x.assayedFineness < x.declaredFineness - 0.02)) {
      out.push({
        id: `EX-${n}-P${r.id.slice(2)}`,
        jobId: job.id,
        kind: 'Purity mismatch',
        severity: 'Medium',
        amountFine: r3(r.gross * (r.declaredFineness - (r.assayedFineness ?? 0))),
        summary: `${r.id} declared ${(r.declaredFineness * 100).toFixed(1)}%, assayed ${((r.assayedFineness ?? 0) * 100).toFixed(1)}%`,
        raised: r.date,
      });
    }
    for (const l of s.lots.filter((x) => x.jobId === job.id && !x.acknowledged && daysBetween(x.date, AS_OF) >= 2)) {
      out.push({ id: `EX-${n}-A${l.id.slice(2)}`, jobId: job.id, kind: 'Unacknowledged lot', severity: 'Medium', amountFine: fine(l.gross, l.fineness), summary: `${l.id} unacknowledged for ${daysBetween(l.date, AS_OF)} days`, raised: l.date });
    }
    if (isOverdue(s, job)) {
      out.push({ id: `EX-${n}-D`, jobId: job.id, kind: 'Overdue job', severity: 'Low', amountFine: null, summary: `Deadline ${job.deadline} passed ${daysBetween(job.deadline, AS_OF)} days ago`, raised: job.deadline });
    }
  }
  const rank = { High: 0, Medium: 1, Low: 2 };
  return out.sort((a, b) => rank[a.severity] - rank[b.severity] || b.raised.localeCompare(a.raised));
}

/* --------------------------------------------------------------- settlement */

export interface SettlementLine {
  jobId: string;
  partyId: string;
  finishedGross: number;
  labour: number;
  allowanceFine: number;
  varianceFine: number;
  excessFine: number;
  recovery: number;
  outstandingFine: number;
  net: number;
}

/** Labour on finished-goods gross at the karigar's rate; excess wastage recovered at the reference gold rate. */
export function settlementFor(s: AppState, job: Job): SettlementLine | null {
  const rets = s.returns.filter((r) => r.jobId === job.id);
  if (!rets.length) return null;
  const fg = rets.filter((r) => r.type === 'Finished goods');
  const partyId = (fg[0] ?? rets[0]).from;
  const rate = s.parties.find((p) => p.id === partyId)?.labourRate ?? 0;
  const finishedGross = r3(fg.reduce((a, r) => a + r.gross, 0));
  const rec = reconcile(s, job);
  const labour = Math.round(finishedGross * rate);
  const recovery = Math.round(rec.unexplainedFine * GOLD_RATE_PER_FINE_G);
  return {
    jobId: job.id,
    partyId,
    finishedGross,
    labour,
    allowanceFine: rec.allowanceFine,
    varianceFine: rec.varianceFine,
    excessFine: rec.unexplainedFine,
    recovery,
    outstandingFine: rec.outstandingFine,
    net: labour - recovery,
  };
}

/* ---------------------------------------------------------------- formatting */

export const g3 = (n: number) => `${n.toLocaleString('en-IN', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} g`;
export const pct = (f: number) => `${(f * 100).toFixed(1)}%`;
export const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;
export const fmtDate = (d: string) => new Date(d + (d.length === 10 ? 'T00:00' : '')).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
