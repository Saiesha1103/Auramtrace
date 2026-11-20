/** Domain types for the AURUMTRACE internal app. Weights are grams; fineness is parts per 1 (0.916 = 22K). */

export type Role = 'Manufacturer' | 'Head karigar' | 'Karigar' | 'Subcontractor';

export interface Party {
  id: string;
  name: string;
  role: Role;
  parentId: string | null;
  unit: string;
  skills: string[];
  /** labour rate, ₹ per gram of finished goods */
  labourRate: number;
  since: string;
}

/**
 * Measurement provenance (PRD: evidence-grade weighing). Prototype data is
 * manual entry only — no scale integration exists, so 'Device' is never used.
 */
export interface Measurement {
  scaleId: string;
  operator: string;
  method: 'Manual entry' | 'Imported';
}

export type JobStatus = 'Draft' | 'Issued' | 'In production' | 'Returned' | 'Reconciled' | 'Settled';

export interface Job {
  id: string;
  title: string;
  orderRef: string;
  karat: '24K' | '22K' | '18K';
  fineness: number;
  pieces: number;
  targetGrossPerPiece: number;
  headKarigarId: string;
  lossAllowancePct: number;
  createdAt: string;
  deadline: string;
  notes: string;
  /** set when settlement is approved */
  settled?: boolean;
}

export interface Lot {
  id: string;
  jobId: string;
  issuedTo: string;
  gross: number;
  fineness: number;
  date: string;
  source: string;
  acknowledged: boolean;
  ackAt?: string;
  /** job-work challan / internal issue record reference */
  challanRef?: string;
  measurement?: Measurement;
}

export type TransferKind = 'Full' | 'Partial' | 'Split';

export interface Transfer {
  id: string;
  jobId: string;
  from: string;
  to: string;
  gross: number;
  fineness: number;
  date: string;
  kind: TransferKind;
  purpose: string;
  challanRef?: string;
  /** receiver signed for the metal */
  acknowledged: boolean;
  ackAt?: string;
}

export type Stage = 'Alloying' | 'Casting' | 'Filing' | 'Setting' | 'Polishing' | 'QC';
export const STAGES: Stage[] = ['Alloying', 'Casting', 'Filing', 'Setting', 'Polishing', 'QC'];

export interface ProductionEntry {
  id: string;
  jobId: string;
  stage: Stage;
  partyId: string;
  date: string;
  inGross: number;
  outGross: number;
  pieces: number;
  status: 'Done' | 'In progress';
  note?: string;
  measurement?: Measurement;
}

export type ReturnType = 'Finished goods' | 'Scrap' | 'Dust & sweep' | 'WIP';

export interface ReturnEntry {
  id: string;
  jobId: string;
  from: string;
  type: ReturnType;
  gross: number;
  declaredFineness: number;
  /** assay result where tested; reconciliation uses this when present */
  assayedFineness?: number;
  pieces: number;
  date: string;
  partial: boolean;
  /** stones / non-metal components inside gross; excluded before fine-gold calculation */
  stoneWeight?: number;
  measurement?: Measurement;
}

export interface EvidenceDoc {
  id: string;
  jobId: string;
  kind: 'Assay report' | 'Weighing slip' | 'Calibration log' | 'Photo' | 'Acknowledgement';
  title: string;
  detail: string;
  date: string;
}

export type SettlementStatus = 'Draft' | 'Pending approval' | 'Approved' | 'On hold';

export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  /** 'seed' = synthetic history; 'local-demo' = action taken in this browser session, not sent anywhere */
  source: 'seed' | 'local-demo';
}
