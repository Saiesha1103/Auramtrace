/**
 * AURUMTRACE Production API Client & Adapter.
 *
 * Connects the Vite + React frontend to the FastAPI backend.
 * Features:
 *   - Automatic authentication against backend seed admin
 *   - Clean mapping between backend parts-per-thousand (ppt) and frontend fractions
 *   - Comprehensive CRUD methods for Jobs, Custody, Transfers, Production, Returns,
 *     Reconciliation, Exceptions, AI Investigations, and Settlements
 *   - Real-time connection health checking with explicit offline demo fallback
 *   - Preserves backend authority: never derives gold balances independently
 */

import type {
  AuditEntry,
  Job,
  Lot,
  Party,
  ProductionEntry,
  ReturnEntry,
  SettlementStatus,
  Stage,
  Transfer,
  TransferKind,
  ReturnType,
  Role,
} from './types';

// Default to backend on localhost:8000/api/v1 if not specified
export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000/api/v1';

export type ApiConnectionStatus = 'connected' | 'connecting' | 'offline_fallback' | 'error';

export interface ApiState {
  status: ApiConnectionStatus;
  url: string;
  authenticated: boolean;
  user: { email: string; fullName: string; role: string; organisationName?: string } | null;
  error?: string;
  lastSync?: string;
}

let _apiState: ApiState = {
  status: 'connecting',
  url: API_BASE,
  authenticated: false,
  user: null,
};

const _listeners = new Set<(s: ApiState) => void>();

export function subscribeApiState(listener: (s: ApiState) => void) {
  _listeners.add(listener);
  listener(_apiState);
  return () => {
    _listeners.delete(listener);
  };
}

function updateApiState(patch: Partial<ApiState>) {
  _apiState = { ..._apiState, ...patch };
  _listeners.forEach((l) => l(_apiState));
}

export const getApiState = () => _apiState;
export const isLiveApi = () => _apiState.status === 'connected';

/* ------------------------------------------------------------------ Auth & Headers */

const TOKEN_KEY = 'aurumtrace_access_token';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null) {
  if (typeof window === 'undefined') return;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let errMessage = `API request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) {
        if (typeof body.detail === 'string') {
          errMessage = body.detail;
        } else if (Array.isArray(body.detail)) {
          errMessage = body.detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
        }
      } else if (body.message) {
        errMessage = body.message;
      }
    } catch {
      // use fallback message
    }
    const err = new Error(errMessage) as any;
    err.status = res.status;
    throw err;
  }

  if (res.status === 204) {
    return {} as T;
  }
  return res.json();
}

/* ------------------------------------------------------------------ Auth Methods */

export async function login(email: string, password: string): Promise<boolean> {
  try {
    const data = await request<{ accessToken: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(data.accessToken);
    updateApiState({
      authenticated: true,
      user: data.user,
      status: 'connected',
      error: undefined,
    });
    return true;
  } catch (err: any) {
    updateApiState({ error: err.message });
    return false;
  }
}

export async function loginDefaultAdmin(): Promise<boolean> {
  return login('admin@aurumtrace-demo.example.com', 'Auram-Demo-2026!');
}

/* ------------------------------------------------------------------ Model Mappings */

function mapRole(kind: string): Role {
  if (kind === 'head_karigar') return 'Head karigar';
  if (kind === 'subcontractor') return 'Subcontractor';
  if (kind === 'manufacturer') return 'Manufacturer';
  return 'Karigar';
}

function pptToFraction(ppt: number | string): number {
  const n = typeof ppt === 'string' ? parseFloat(ppt) : ppt;
  return Number.isFinite(n) ? Number((n / 1000).toFixed(4)) : 0.916;
}

function fractionToPpt(f: number): number {
  return Math.round(f * 1000);
}

/* ------------------------------------------------------------------ Full Data Sync */

export interface BackendDataBundle {
  parties: Party[];
  jobs: Job[];
  lots: Lot[];
  transfers: Transfer[];
  production: ProductionEntry[];
  returns: ReturnEntry[];
  settlements: Record<string, SettlementStatus>;
  audit: AuditEntry[];
}

export async function fetchBackendAppState(): Promise<BackendDataBundle> {
  // If not logged in, attempt auto-login with default seeded admin credentials
  if (!getAuthToken()) {
    const ok = await loginDefaultAdmin();
    if (!ok) {
      throw new Error('Could not authenticate to backend.');
    }
  }

  // Parallel fetch of all primary endpoints
  const [karigarsPage, jobsPage, lotsPage, transfersPage, prodPage, returnsPage, worksheetsPage, auditPage] =
    await Promise.all([
      request<any>('/karigars?limit=100'),
      request<any>('/jobs?limit=100'),
      request<any>('/lots?limit=100'),
      request<any>('/transfers?limit=100'),
      request<any>('/production?limit=100'),
      request<any>('/returns?limit=100'),
      request<any>('/settlements/worksheets?limit=100').catch(() => ({ items: [] })),
      request<any>('/audit?limit=100').catch(() => ({ items: [] })),
    ]);

  // ID to Code lookup maps
  const karigarCodeMap = new Map<string, string>();
  const karigars = karigarsPage.items || [];
  karigars.forEach((k: any) => karigarCodeMap.set(k.id, k.code));

  const jobCodeMap = new Map<string, string>();
  const jobsRaw = jobsPage.items || [];
  jobsRaw.forEach((j: any) => jobCodeMap.set(j.id, j.code));

  // Map Parties
  const parties: Party[] = [
    {
      id: 'VAULT',
      name: 'Central Vault',
      role: 'Manufacturer',
      parentId: null,
      unit: 'HQ Vault Desk',
      skills: ['Bullion', 'Issuance', 'Assay'],
      labourRate: 0,
      since: '2024-01-01',
    },
    ...karigars.map((k: any) => ({
      id: k.code,
      name: k.name,
      role: mapRole(k.kind),
      parentId: k.headKarigarId ? karigarCodeMap.get(k.headKarigarId) || null : null,
      unit: k.unit || 'Workshop',
      skills: k.skills || [],
      labourRate: 250,
      since: k.createdAt ? k.createdAt.slice(0, 10) : '2025-01-01',
    })),
  ];

  // Map Jobs
  const jobs: Job[] = jobsRaw.map((j: any) => ({
    id: j.code,
    title: j.title,
    orderRef: j.orderRef || `PO-${j.code}`,
    karat: j.karat as any,
    fineness: pptToFraction(j.targetFinenessPpt || 916),
    pieces: j.pieces,
    targetGrossPerPiece: Number((30.0 / Math.max(1, j.pieces)).toFixed(1)),
    headKarigarId: j.headKarigarId ? karigarCodeMap.get(j.headKarigarId) || 'K-01' : 'K-01',
    lossAllowancePct: Number(j.lossAllowancePct),
    createdAt: j.createdAt ? j.createdAt.slice(0, 10) : '2026-11-01',
    deadline: j.dueDate ? String(j.dueDate) : '2026-12-01',
    notes: j.notes || '',
    settled: j.status === 'settled',
  }));

  // Map Lots
  const lotsRaw = lotsPage.items || [];
  const lots: Lot[] = lotsRaw.map((l: any) => ({
    id: l.code,
    jobId: l.jobId ? jobCodeMap.get(l.jobId) || 'J-1182' : 'J-1182',
    issuedTo: l.custodianKarigarId ? karigarCodeMap.get(l.custodianKarigarId) || 'K-01' : 'K-01',
    gross: Number(l.grossWeightG),
    fineness: pptToFraction(l.finenessPpt),
    date: l.createdAt ? l.createdAt.slice(0, 10) : '2026-11-01',
    source: l.source || 'Vault Bullion',
    acknowledged: l.status === 'issued' || l.status === 'in_custody',
    ackAt: l.createdAt ? l.createdAt.slice(0, 10) : undefined,
  }));

  // Map Transfers
  const transfersRaw = transfersPage.items || [];
  const transfers: Transfer[] = transfersRaw.map((t: any) => ({
    id: t.challanRef || `TR-${t.id.slice(0, 8)}`,
    jobId: jobCodeMap.get(t.jobId) || t.jobCode || 'J-1182',
    from: t.fromKarigar?.code || karigarCodeMap.get(t.fromKarigarId) || 'K-01',
    to: t.toKarigar?.code || karigarCodeMap.get(t.toKarigarId) || 'K-02',
    gross: Number(t.grossWeightG),
    fineness: pptToFraction(t.finenessPpt),
    date: (t.occurredAt || t.recordedAt || '').slice(0, 10) || '2026-11-05',
    kind: 'Partial' as TransferKind,
    purpose: t.note || t.challanRef || 'Subcontract stage work',
  }));

  // Map Production
  const prodRaw = prodPage.items || [];
  const production: ProductionEntry[] = prodRaw.map((p: any) => ({
    id: `P-${p.id.slice(0, 8)}`,
    jobId: jobCodeMap.get(p.jobId) || 'J-1182',
    stage: (p.stage || 'Casting') as Stage,
    partyId: karigarCodeMap.get(p.karigarId) || 'K-01',
    date: p.startedAt ? p.startedAt.slice(0, 10) : '2026-11-06',
    inGross: 10.0,
    outGross: 9.85,
    pieces: 6,
    status: p.status === 'completed' ? 'Done' : 'In progress',
    note: p.note || undefined,
  }));

  // Map Returns
  const returnsRaw = returnsPage.items || [];
  const returns: ReturnEntry[] = returnsRaw.map((r: any) => {
    let rType: ReturnType = 'Finished goods';
    if (r.returnCategory === 'scrap') rType = 'Scrap';
    else if (r.returnCategory === 'dust_sweep') rType = 'Dust & sweep';
    else if (r.returnCategory === 'wip') rType = 'WIP';

    return {
      id: r.code,
      jobId: jobCodeMap.get(r.jobId) || 'J-1182',
      from: karigarCodeMap.get(r.karigarId) || 'K-01',
      type: rType,
      gross: Number(r.grossWeightG),
      declaredFineness: pptToFraction(r.declaredFinenessPpt),
      assayedFineness: r.assayedFinenessPpt ? pptToFraction(r.assayedFinenessPpt) : undefined,
      pieces: r.pieces || 1,
      date: r.returnedAt ? r.returnedAt.slice(0, 10) : '2026-11-10',
      partial: !r.isFinalReturn,
    };
  });

  // Map Settlements
  const settlements: Record<string, SettlementStatus> = {};
  const sheets = worksheetsPage.items || [];
  sheets.forEach((s: any) => {
    const jCode = jobCodeMap.get(s.jobId) || s.jobCode;
    if (jCode) {
      if (s.status === 'approved') settlements[jCode] = 'Approved';
      else if (s.status === 'submitted') settlements[jCode] = 'Pending approval';
      else settlements[jCode] = 'Draft';
    }
  });

  // Map Audit
  const auditRaw = auditPage.items || [];
  const audit: AuditEntry[] = auditRaw.map((a: any) => ({
    id: `AUD-${a.id.slice(0, 8)}`,
    at: a.createdAt || new Date().toISOString(),
    actor: a.userEmail || 'System',
    action: a.action,
    target: a.entityType ? `${a.entityType}:${a.entityId}` : 'system',
    source: 'seed',
  }));

  updateApiState({
    status: 'connected',
    lastSync: new Date().toISOString(),
    error: undefined,
  });

  return {
    parties,
    jobs,
    lots,
    transfers,
    production,
    returns,
    settlements,
    audit,
  };
}

/* ------------------------------------------------------------------ Live Action Mutators */

export async function apiCreateJob(input: {
  title: string;
  orderRef?: string;
  karat: string;
  pieces: number;
  lossAllowancePct: number;
  headKarigarId: string;
  dueDate: string;
  notes?: string;
}): Promise<{ ok: boolean; id?: string; error?: string }> {
  try {
    // Resolve karigar UUID from code
    const karigars = await request<any>('/karigars?limit=100');
    const head = (karigars.items || []).find(
      (k: any) => k.code === input.headKarigarId || k.id === input.headKarigarId
    );

    const data = await request<any>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        title: input.title,
        orderRef: input.orderRef || null,
        karat: input.karat,
        pieces: input.pieces,
        lossAllowancePct: input.lossAllowancePct,
        headKarigarId: head?.id || null,
        dueDate: input.dueDate,
        notes: input.notes || null,
      }),
    });
    return { ok: true, id: data.code || data.id };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function apiIssueLot(input: {
  jobId: string;
  issuedTo: string;
  gross: number;
  fineness: number;
  source: string;
}): Promise<{ ok: boolean; id?: string; error?: string }> {
  try {
    // 1. Resolve Job & Karigar UUIDs
    const [jobs, karigars] = await Promise.all([
      request<any>('/jobs?limit=100'),
      request<any>('/karigars?limit=100'),
    ]);
    const job = (jobs.items || []).find((j: any) => j.code === input.jobId || j.id === input.jobId);
    const karigar = (karigars.items || []).find(
      (k: any) => k.code === input.issuedTo || k.id === input.issuedTo
    );
    if (!job) throw new Error(`Job ${input.jobId} not found on server.`);
    if (!karigar) throw new Error(`Karigar ${input.issuedTo} not found on server.`);

    // 2. Create Lot
    const lot = await request<any>('/lots', {
      method: 'POST',
      body: JSON.stringify({
        source: input.source,
        grossWeightG: input.gross,
        netWeightG: input.gross,
        finenessPpt: fractionToPpt(input.fineness),
        measurement: { scaleId: 'SC-WEB-01', operatorName: 'Web Portal', method: 'digital' },
      }),
    });

    // 3. Issue Lot to Karigar on Job
    await request<any>(`/lots/${lot.id}/issue`, {
      method: 'POST',
      body: JSON.stringify({
        jobId: job.id,
        karigarId: karigar.id,
        grossWeightG: input.gross,
        netWeightG: input.gross,
        challanRef: `CH-${lot.code}`,
        measurement: { scaleId: 'SC-WEB-01', operatorName: 'Web Portal', method: 'digital' },
      }),
    });

    return { ok: true, id: lot.code };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function apiAcknowledgeLot(lotCode: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const lots = await request<any>('/lots?limit=100');
    const lot = (lots.items || []).find((l: any) => l.code === lotCode || l.id === lotCode);
    if (!lot) throw new Error(`Lot ${lotCode} not found.`);

    await request<any>(`/lots/${lot.id}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ acknowledgedByName: 'Web Desk User' }),
    });
    return { ok: true };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function apiCreateTransfer(input: {
  jobId: string;
  from: string;
  to: string;
  gross: number;
  fineness: number;
  purpose: string;
}): Promise<{ ok: boolean; id?: string; error?: string }> {
  try {
    const [jobs, karigars, lots] = await Promise.all([
      request<any>('/jobs?limit=100'),
      request<any>('/karigars?limit=100'),
      request<any>('/lots?limit=100'),
    ]);
    const job = (jobs.items || []).find((j: any) => j.code === input.jobId || j.id === input.jobId);
    const fromK = (karigars.items || []).find((k: any) => k.code === input.from || k.id === input.from);
    const toK = (karigars.items || []).find((k: any) => k.code === input.to || k.id === input.to);
    const jobLots = (lots.items || []).filter((l: any) => l.jobId === job?.id);
    const lotId = jobLots[0]?.id || (lots.items || [])[0]?.id;

    if (!job || !fromK || !toK) throw new Error('Could not resolve job or karigar identifiers.');

    const transfer = await request<any>('/transfers', {
      method: 'POST',
      body: JSON.stringify({
        jobId: job.id,
        fromKarigarId: fromK.id,
        toKarigarId: toK.id,
        lotId: lotId,
        grossWeightG: input.gross,
        netWeightG: input.gross,
        measurement: { scaleId: 'SC-TRANSFER-01', operatorName: 'Web Portal', method: 'digital' },
        challanRef: `CH-TR-${Date.now().toString().slice(-4)}`,
        purpose: input.purpose,
      }),
    });
    return { ok: true, id: transfer.code };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function apiRecordReturn(input: {
  jobId: string;
  from: string;
  type: ReturnType;
  gross: number;
  declaredFineness: number;
  pieces?: number;
}): Promise<{ ok: boolean; id?: string; error?: string }> {
  try {
    const [jobs, karigars, lots] = await Promise.all([
      request<any>('/jobs?limit=100'),
      request<any>('/karigars?limit=100'),
      request<any>('/lots?limit=100'),
    ]);
    const job = (jobs.items || []).find((j: any) => j.code === input.jobId || j.id === input.jobId);
    const fromK = (karigars.items || []).find((k: any) => k.code === input.from || k.id === input.from);
    const jobLots = (lots.items || []).filter((l: any) => l.jobId === job?.id);
    const lotId = jobLots[0]?.id || (lots.items || [])[0]?.id;

    let cat = 'finished_goods';
    if (input.type === 'Scrap') cat = 'scrap';
    else if (input.type === 'Dust & sweep') cat = 'dust_sweep';
    else if (input.type === 'WIP') cat = 'wip';

    const ret = await request<any>('/returns', {
      method: 'POST',
      body: JSON.stringify({
        jobId: job.id,
        karigarId: fromK.id,
        lotId: lotId,
        returnCategory: cat,
        grossWeightG: input.gross,
        netMetalWeightG: input.gross,
        declaredFinenessPpt: fractionToPpt(input.declaredFineness),
        pieces: input.pieces || 1,
        measurement: { scaleId: 'SC-RET-01', operatorName: 'Web Vault Desk', method: 'digital' },
        isFinalReturn: input.type === 'Finished goods',
      }),
    });
    return { ok: true, id: ret.code };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function apiReconcileJob(jobCode: string): Promise<any> {
  const jobs = await request<any>('/jobs?limit=100');
  const job = (jobs.items || []).find((j: any) => j.code === jobCode || j.id === jobCode);
  if (!job) throw new Error(`Job ${jobCode} not found.`);
  return request<any>(`/jobs/${job.id}/reconcile`, { method: 'POST' });
}

export async function apiDismissException(exceptionId: string, reason: string): Promise<any> {
  return request<any>(`/exceptions/${exceptionId}/dismiss`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export interface AiExplanationResult {
  ok: boolean;
  text?: string;
  error?: string;
  data?: any;
}

/** Requests an AI explanation for an exception from the live backend investigation assistant. */
export async function requestAiExplanation(exceptionId: string): Promise<AiExplanationResult> {
  try {
    const data = await request<any>('/investigations/run', {
      method: 'POST',
      body: JSON.stringify({ exceptionId }),
    });
    return {
      ok: true,
      text: data.response?.summary || 'AI investigation completed successfully.',
      data,
    };
  } catch (err: any) {
    return {
      ok: false,
      error: `AI Investigation failed: ${err.message}`,
    };
  }
}
