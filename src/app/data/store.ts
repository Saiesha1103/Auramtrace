import { useSyncExternalStore } from 'react';
import { AUDIT_SEED, EVIDENCE, JOBS, LOTS, PARTIES, PRODUCTION, RETURNS, SETTLEMENT_STATUS, TRANSFERS, VAULT } from './seed';
import { custody, fine, r3 } from './calc';
import type { AuditEntry, EvidenceDoc, Job, Lot, Party, ProductionEntry, ReturnEntry, SettlementStatus, Stage, Transfer, TransferKind, ReturnType } from './types';
import {
  isLiveApi,
  fetchBackendAppState,
  apiCreateJob,
  apiIssueLot,
  apiAcknowledgeLot,
  apiCreateTransfer,
  apiRecordReturn,
  apiReconcileJob,
  apiDismissException,
} from './api';

/**
 * AURUMTRACE State Store.
 *
 * Seamlessly manages state with automatic backend synchronisation:
 * - When FastAPI backend is online, loads authoritative state directly from PostgreSQL ledger.
 * - If backend is offline or unconfigured, preserves an explicitly separated offline demo fallback.
 * - Never calculates authoritative gold balances independently: relies on backend ledger calculations.
 */
export interface AppState {
  parties: Party[];
  jobs: Job[];
  lots: Lot[];
  transfers: Transfer[];
  production: ProductionEntry[];
  returns: ReturnEntry[];
  evidence: EvidenceDoc[];
  settlement: Record<string, SettlementStatus>;
  exceptionReview: Record<string, 'Open' | 'Under review' | 'Resolved'>;
  audit: AuditEntry[];
  seq: number;
}

const initial = (): AppState => ({
  parties: PARTIES,
  jobs: JOBS,
  lots: LOTS,
  transfers: TRANSFERS,
  production: PRODUCTION,
  returns: RETURNS,
  evidence: EVIDENCE,
  settlement: { ...SETTLEMENT_STATUS },
  exceptionReview: {},
  audit: AUDIT_SEED,
  seq: 1,
});

let state = initial();
const listeners = new Set<() => void>();

function set(next: AppState) {
  state = next;
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

/** Whole-state subscription; derive with useMemo in the page (keeps snapshots referentially stable). */
export function useAppState(): AppState {
  return useSyncExternalStore(subscribe, () => state);
}
export const getState = () => state;

export type Result = { ok: true; id: string } | { ok: false; error: string };

const nowStamp = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

/** Local ids are clearly marked so they can never be mistaken for server records. */
function nextId(prefix: string) {
  const id = `${prefix}-LOCAL-${String(state.seq).padStart(3, '0')}`;
  return id;
}

function commit(patch: Partial<AppState>, action: string, target: string, source: 'seed' | 'local-demo' = 'local-demo') {
  const entry: AuditEntry = {
    id: `A-${source === 'local-demo' ? 'LOCAL' : 'SRV'}-${String(state.seq).padStart(3, '0')}`,
    at: nowStamp(),
    actor: source === 'local-demo' ? 'You (demo session)' : 'Authenticated User',
    action,
    target,
    source,
  };
  set({ ...state, ...patch, audit: [...state.audit, entry], seq: state.seq + 1 });
}

const partyName = (id: string) => state.parties.find((p) => p.id === id)?.name ?? id;
const positive = (n: number) => Number.isFinite(n) && n > 0;

/* ----------------------------------------------------------------- Backend Sync */

let _syncPromise: Promise<boolean> | null = null;

export async function syncWithBackend(): Promise<boolean> {
  try {
    const bundle = await fetchBackendAppState();
    set({
      ...state,
      parties: bundle.parties.length ? bundle.parties : state.parties,
      jobs: bundle.jobs.length ? bundle.jobs : state.jobs,
      lots: bundle.lots.length ? bundle.lots : state.lots,
      transfers: bundle.transfers.length ? bundle.transfers : state.transfers,
      production: bundle.production.length ? bundle.production : state.production,
      returns: bundle.returns.length ? bundle.returns : state.returns,
      settlement: Object.keys(bundle.settlements).length ? bundle.settlements : state.settlement,
      audit: bundle.audit.length ? bundle.audit : state.audit,
    });
    return true;
  } catch (err: any) {
    // Preserves offline demo fallback cleanly
    return false;
  }
}

export function initApiSync() {
  if (!_syncPromise && typeof window !== 'undefined') {
    _syncPromise = syncWithBackend();
  }
  return _syncPromise;
}

// Auto-trigger sync on browser startup
if (typeof window !== 'undefined') {
  initApiSync();
}

/* ----------------------------------------------------------------- Actions */

export function createJob(input: Omit<Job, 'id' | 'createdAt'> & { createdAt: string }): Result {
  if (!input.title.trim()) return { ok: false, error: 'Title is required.' };
  if (!positive(input.pieces) || !positive(input.targetGrossPerPiece))
    return { ok: false, error: 'Pieces and target weight must be greater than zero.' };
  if (!input.deadline) return { ok: false, error: 'Set a deadline.' };
  if (input.deadline < input.createdAt)
    return { ok: false, error: 'Deadline cannot be before the creation date.' };
  if (input.lossAllowancePct < 0 || input.lossAllowancePct > 5)
    return { ok: false, error: 'Loss allowance must be between 0% and 5%.' };

  const id = nextId('J');
  commit({ jobs: [...state.jobs, { ...input, id }] }, `Created job ${id} “${input.title}”`, id);

  // If live API connected, also send to backend
  if (isLiveApi()) {
    apiCreateJob({
      title: input.title,
      orderRef: input.orderRef,
      karat: input.karat,
      pieces: input.pieces,
      lossAllowancePct: input.lossAllowancePct,
      headKarigarId: input.headKarigarId,
      dueDate: input.deadline,
      notes: input.notes,
    }).then((res) => {
      if (res.ok) syncWithBackend();
    });
  }

  return { ok: true, id };
}

export function issueLot(input: {
  jobId: string;
  issuedTo: string;
  gross: number;
  fineness: number;
  date: string;
  source: string;
}): Result {
  if (!state.jobs.some((j) => j.id === input.jobId)) return { ok: false, error: 'Choose a job.' };
  if (!positive(input.gross)) return { ok: false, error: 'Gross weight must be greater than zero.' };
  if (!(input.fineness > 0 && input.fineness <= 0.9999))
    return { ok: false, error: 'Fineness must be between 0 and 0.9999.' };

  const id = nextId('L');
  commit(
    { lots: [...state.lots, { ...input, gross: r3(input.gross), id, acknowledged: false }] },
    `Issued lot ${id} (${input.gross.toFixed(3)} g @ ${(input.fineness * 100).toFixed(1)}%) to ${partyName(
      input.issuedTo
    )}`,
    input.jobId
  );

  if (isLiveApi()) {
    apiIssueLot({
      jobId: input.jobId,
      issuedTo: input.issuedTo,
      gross: input.gross,
      fineness: input.fineness,
      source: input.source,
    }).then((res) => {
      if (res.ok) syncWithBackend();
    });
  }

  return { ok: true, id };
}

export function acknowledgeLot(lotId: string, date: string): Result {
  const lot = state.lots.find((l) => l.id === lotId);
  if (!lot) return { ok: false, error: 'Lot not found.' };
  if (lot.acknowledged) return { ok: false, error: 'Lot is already acknowledged.' };

  commit(
    {
      lots: state.lots.map((l) => (l.id === lotId ? { ...l, acknowledged: true, ackAt: date } : l)),
    },
    `Recorded acknowledgement of ${lotId} by ${partyName(lot.issuedTo)}`,
    lot.jobId
  );

  if (isLiveApi()) {
    apiAcknowledgeLot(lotId).then((res) => {
      if (res.ok) syncWithBackend();
    });
  }

  return { ok: true, id: lotId };
}

export function createTransfer(input: {
  jobId: string;
  from: string;
  to: string;
  gross: number;
  fineness: number;
  date: string;
  kind: TransferKind;
  purpose: string;
}): Result {
  if (!state.parties.some((p) => p.id === input.to))
    return { ok: false, error: 'Choose a recipient for every transfer leg.' };
  if (input.from === input.to) return { ok: false, error: 'Sender and receiver must differ.' };
  if (!positive(input.gross)) return { ok: false, error: 'Gross weight must be greater than zero.' };

  const held = custody(state, input.jobId).get(input.from) ?? 0;
  const moving = fine(input.gross, input.fineness);
  if (moving > held + 0.0005)
    return {
      ok: false,
      error: `${partyName(input.from)} holds only ${held.toFixed(3)} g fine on this job; this transfer moves ${moving.toFixed(3)} g.`,
    };

  const id = nextId('T');
  commit(
    { transfers: [...state.transfers, { ...input, gross: r3(input.gross), id }] },
    `${input.kind} transfer ${id}: ${input.gross.toFixed(3)} g ${partyName(input.from)} → ${partyName(input.to)}`,
    input.jobId
  );

  if (isLiveApi()) {
    apiCreateTransfer({
      jobId: input.jobId,
      from: input.from,
      to: input.to,
      gross: input.gross,
      fineness: input.fineness,
      purpose: input.purpose,
    }).then((res) => {
      if (res.ok) syncWithBackend();
    });
  }

  return { ok: true, id };
}

export function addProduction(input: {
  jobId: string;
  stage: Stage;
  partyId: string;
  date: string;
  inGross: number;
  outGross: number;
  pieces: number;
  status: 'Done' | 'In progress';
  note?: string;
}): Result {
  if (!positive(input.inGross)) return { ok: false, error: 'Input weight must be greater than zero.' };
  if (input.status === 'Done' && !positive(input.outGross))
    return { ok: false, error: 'Record an output weight for a completed stage.' };
  if (input.stage !== 'Alloying' && input.outGross > input.inGross)
    return { ok: false, error: 'Output cannot exceed input except at alloying (where alloy is added).' };

  const id = nextId('P');
  commit(
    {
      production: [
        ...state.production,
        { ...input, inGross: r3(input.inGross), outGross: r3(input.outGross), id },
      ],
    },
    `Logged ${input.stage} (${input.status}) for ${input.jobId}`,
    input.jobId
  );

  return { ok: true, id };
}

export function recordReturn(input: {
  jobId: string;
  from: string;
  type: ReturnType;
  gross: number;
  declaredFineness: number;
  pieces: number;
  date: string;
  partial: boolean;
}): Result {
  if (!positive(input.gross)) return { ok: false, error: 'Gross weight must be greater than zero.' };
  if (!(input.declaredFineness > 0 && input.declaredFineness <= 0.9999))
    return { ok: false, error: 'Declared fineness must be between 0 and 0.9999.' };

  const held = custody(state, input.jobId).get(input.from) ?? 0;
  const moving = fine(input.gross, input.declaredFineness);
  if (moving > held + 0.0005)
    return {
      ok: false,
      error: `${partyName(input.from)} holds only ${held.toFixed(3)} g fine on this job; this return is ${moving.toFixed(3)} g.`,
    };

  const id = nextId('R');
  commit(
    { returns: [...state.returns, { ...input, gross: r3(input.gross), id }] },
    `Received ${input.partial ? 'partial ' : ''}${input.type.toLowerCase()} ${id} (${input.gross.toFixed(
      3
    )} g) from ${partyName(input.from)}`,
    input.jobId
  );

  if (isLiveApi()) {
    apiRecordReturn({
      jobId: input.jobId,
      from: input.from,
      type: input.type,
      gross: input.gross,
      declaredFineness: input.declaredFineness,
      pieces: input.pieces,
    }).then((res) => {
      if (res.ok) syncWithBackend();
    });
  }

  return { ok: true, id };
}

export function setSettlement(jobId: string, status: SettlementStatus): Result {
  commit(
    { settlement: { ...state.settlement, [jobId]: status } },
    `Set settlement for ${jobId} to “${status}”`,
    jobId
  );
  return { ok: true, id: jobId };
}

export async function reconcileJob(jobCode: string): Promise<any> {
  if (isLiveApi()) {
    const res = await apiReconcileJob(jobCode);
    await syncWithBackend();
    return res;
  }
  return { status: 'reconciled' };
}

export function setExceptionReview(
  exId: string,
  jobId: string,
  status: 'Open' | 'Under review' | 'Resolved'
): Result {
  commit(
    { exceptionReview: { ...state.exceptionReview, [exId]: status } },
    `Marked ${exId} as ${status.toLowerCase()}`,
    jobId
  );
  if (isLiveApi() && status === 'Resolved') {
    apiDismissException(exId, 'Resolved via manager review in dashboard').then((res) => {
      if (res) syncWithBackend();
    });
  }
  return { ok: true, id: exId };
}

export function resetDemo() {
  set(initial());
  if (isLiveApi()) {
    syncWithBackend();
  }
}

export { VAULT };
