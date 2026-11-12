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
