import type { AuditEntry, EvidenceDoc, Job, Lot, Party, ProductionEntry, ReturnEntry, SettlementStatus, Transfer } from './types';

/**
 * SYNTHETIC DEMO DATA — no AURUMTRACE API is available in this repository.
 * Every figure below is invented for the prototype and is internally consistent
 * (fine gold = gross × fineness, rounded to 0.001 g).
 *
 * All "as of" comparisons (overdue, ageing) use AS_OF, never the wall clock,
 * so every calculation is deterministic.
 */
export const AS_OF = '2026-11-12';
export const VAULT = 'VAULT';

export const PARTIES: Party[] = [
  { id: VAULT, name: 'Vault · Manufacturer', role: 'Manufacturer', parentId: null, unit: 'Head office, Zaveri Bazaar', skills: ['Issue', 'Assay', 'Settlement'], labourRate: 0, since: '2014-04-01' },
  { id: 'K-01', name: 'Mahesh Soni', role: 'Head karigar', parentId: VAULT, unit: 'Unit A · Zaveri Bazaar', skills: ['Casting', 'Bangles', 'Team lead'], labourRate: 210, since: '2016-06-12' },
  { id: 'K-02', name: 'Farida Shaikh', role: 'Head karigar', parentId: VAULT, unit: 'Unit B · Kalbadevi', skills: ['Temple work', 'Chains', 'Team lead'], labourRate: 220, since: '2017-02-03' },
  { id: 'K-03', name: 'Ravi Kumar', role: 'Karigar', parentId: 'K-01', unit: 'Unit A · Zaveri Bazaar', skills: ['Alloying', 'Casting', 'Filing'], labourRate: 165, since: '2019-08-19' },
  { id: 'K-05', name: 'Suresh Pal', role: 'Karigar', parentId: 'K-01', unit: 'Unit A · Zaveri Bazaar', skills: ['Stone setting', 'Polishing'], labourRate: 180, since: '2020-01-07' },
  { id: 'K-07', name: 'Anil Verma', role: 'Karigar', parentId: 'K-02', unit: 'Unit B · Kalbadevi', skills: ['Bangles', 'Temple work', 'Filing'], labourRate: 175, since: '2018-11-26' },
  { id: 'K-08', name: 'Kavita Jadhav', role: 'Karigar', parentId: 'K-02', unit: 'Unit B · Kalbadevi', skills: ['Chains', 'Polishing'], labourRate: 170, since: '2021-03-15' },
  { id: 'S-01', name: 'Shree Casting Works', role: 'Subcontractor', parentId: 'K-01', unit: 'Andheri East', skills: ['Lost-wax casting'], labourRate: 95, since: '2018-05-02' },
  { id: 'S-03', name: 'Om Polish & Finish', role: 'Subcontractor', parentId: 'K-02', unit: 'Bhuleshwar', skills: ['Casting', 'Finishing', 'Rhodium'], labourRate: 110, since: '2019-09-30' },
];

export const JOBS: Job[] = [
  { id: 'J-1160', title: 'Antique jhumka pairs', orderRef: 'SO-4410', karat: '22K', fineness: 0.916, pieces: 12, targetGrossPerPiece: 3.6, headKarigarId: 'K-01', lossAllowancePct: 1.0, createdAt: '2026-10-20', deadline: '2026-11-01', notes: 'Antique finish, screw-back posts.', settled: true },
  { id: 'J-1168', title: 'Kada bracelets', orderRef: 'SO-4422', karat: '22K', fineness: 0.916, pieces: 4, targetGrossPerPiece: 13.2, headKarigarId: 'K-01', lossAllowancePct: 1.5, createdAt: '2026-11-04', deadline: '2026-11-10', notes: 'Hollow kada, 2.6" inner diameter, ruby accents.' },
  { id: 'J-1175', title: 'Mangalsutra pendants', orderRef: 'SO-4431', karat: '18K', fineness: 0.75, pieces: 10, targetGrossPerPiece: 2.6, headKarigarId: 'K-01', lossAllowancePct: 0.8, createdAt: '2026-10-24', deadline: '2026-11-08', notes: 'Black bead chain supplied separately.' },
  { id: 'J-1182', title: 'Temple bangles', orderRef: 'SO-4437', karat: '22K', fineness: 0.916, pieces: 6, targetGrossPerPiece: 5.2, headKarigarId: 'K-02', lossAllowancePct: 1.2, createdAt: '2026-11-01', deadline: '2026-11-12', notes: 'Lakshmi motif, matte + high-polish contrast.' },
  { id: 'J-1186', title: 'Solitaire ring mounts', orderRef: 'SO-4440', karat: '18K', fineness: 0.75, pieces: 20, targetGrossPerPiece: 1.6, headKarigarId: 'K-01', lossAllowancePct: 1.0, createdAt: '2026-11-08', deadline: '2026-11-25', notes: '6-prong, sizes 10–16 per order sheet.' },
  { id: 'J-1190', title: 'Rope chain 22"', orderRef: 'SO-4443', karat: '22K', fineness: 0.916, pieces: 3, targetGrossPerPiece: 20, headKarigarId: 'K-02', lossAllowancePct: 1.2, createdAt: '2026-11-05', deadline: '2026-11-20', notes: 'Lobster clasp, hallmark on tag.' },
  { id: 'J-1191', title: 'Coin pendants', orderRef: 'SO-4446', karat: '24K', fineness: 0.995, pieces: 30, targetGrossPerPiece: 1.0, headKarigarId: 'K-02', lossAllowancePct: 0.5, createdAt: '2026-11-09', deadline: '2026-11-18', notes: 'Laxmi-Ganesh die, 1 g each.' },
  { id: 'J-1194', title: 'Nose pins', orderRef: 'SO-4449', karat: '18K', fineness: 0.75, pieces: 40, targetGrossPerPiece: 0.4, headKarigarId: 'K-02', lossAllowancePct: 1.0, createdAt: '2026-11-11', deadline: '2026-12-05', notes: 'Awaiting stone allocation before issue.' },
];

export const LOTS: Lot[] = [
  { id: 'L-3279', jobId: 'J-1160', issuedTo: 'K-01', gross: 40.201, fineness: 0.995, date: '2026-10-21', source: 'Bar 995 · B-778', acknowledged: true, ackAt: '2026-10-21' },
  { id: 'L-3288', jobId: 'J-1175', issuedTo: 'K-01', gross: 20.101, fineness: 0.995, date: '2026-10-25', source: 'Bar 995 · B-781', acknowledged: true, ackAt: '2026-10-25' },
  { id: 'L-3295', jobId: 'J-1168', issuedTo: 'K-01', gross: 50.251, fineness: 0.995, date: '2026-11-04', source: 'Bar 995 · B-790', acknowledged: true, ackAt: '2026-11-04' },
  { id: 'L-3301', jobId: 'J-1182', issuedTo: 'K-02', gross: 30.151, fineness: 0.995, date: '2026-11-02', source: 'Bar 995 · B-792', acknowledged: true, ackAt: '2026-11-02' },
  { id: 'L-3306', jobId: 'J-1190', issuedTo: 'K-02', gross: 60.302, fineness: 0.995, date: '2026-11-05', source: 'Bar 995 · B-795', acknowledged: true, ackAt: '2026-11-05' },
  { id: 'L-3310', jobId: 'J-1186', issuedTo: 'K-01', gross: 25.126, fineness: 0.995, date: '2026-11-09', source: 'Bar 995 · B-797', acknowledged: false },
  { id: 'L-3312', jobId: 'J-1191', issuedTo: 'K-02', gross: 30.151, fineness: 0.995, date: '2026-11-10', source: 'Bar 995 · B-798', acknowledged: true, ackAt: '2026-11-10' },
];

export const TRANSFERS: Transfer[] = [
  { id: 'T-5090', jobId: 'J-1160', from: 'K-01', to: 'K-03', gross: 40.201, fineness: 0.995, date: '2026-10-22', kind: 'Full', purpose: 'Full job to karigar' },
  { id: 'T-5096', jobId: 'J-1175', from: 'K-01', to: 'K-05', gross: 20.101, fineness: 0.995, date: '2026-10-26', kind: 'Full', purpose: 'Full job to karigar' },
  { id: 'T-5101', jobId: 'J-1182', from: 'K-02', to: 'K-07', gross: 30.151, fineness: 0.995, date: '2026-11-02', kind: 'Full', purpose: 'Full job to karigar' },
  { id: 'T-5104', jobId: 'J-1168', from: 'K-01', to: 'K-03', gross: 25.126, fineness: 0.995, date: '2026-11-05', kind: 'Split', purpose: 'Batch A — 2 kadas' },
  { id: 'T-5105', jobId: 'J-1168', from: 'K-01', to: 'S-01', gross: 20.0, fineness: 0.995, date: '2026-11-05', kind: 'Split', purpose: 'Batch B — casting outsourced' },
  { id: 'T-5108', jobId: 'J-1190', from: 'K-02', to: 'K-08', gross: 40.0, fineness: 0.995, date: '2026-11-06', kind: 'Partial', purpose: 'First 2 chains' },
  { id: 'T-5113', jobId: 'J-1168', from: 'K-03', to: 'K-05', gross: 12.0, fineness: 0.916, date: '2026-11-09', kind: 'Partial', purpose: 'Cast kadas to setting' },
  { id: 'T-5112', jobId: 'J-1191', from: 'K-02', to: 'S-03', gross: 15.075, fineness: 0.995, date: '2026-11-10', kind: 'Split', purpose: 'Half batch to die-striking' },
];

export const PRODUCTION: ProductionEntry[] = [
  { id: 'P-901', jobId: 'J-1160', stage: 'Alloying', partyId: 'K-03', date: '2026-10-22', inGross: 40.201, outGross: 43.620, pieces: 0, status: 'Done' },
  { id: 'P-902', jobId: 'J-1160', stage: 'Casting', partyId: 'K-03', date: '2026-10-24', inGross: 43.620, outGross: 43.310, pieces: 24, status: 'Done' },
  { id: 'P-903', jobId: 'J-1160', stage: 'Polishing', partyId: 'K-03', date: '2026-10-29', inGross: 43.310, outGross: 42.900, pieces: 24, status: 'Done' },
  { id: 'P-911', jobId: 'J-1175', stage: 'Alloying', partyId: 'K-05', date: '2026-10-26', inGross: 20.101, outGross: 26.640, pieces: 0, status: 'Done' },
  { id: 'P-912', jobId: 'J-1175', stage: 'Setting', partyId: 'K-05', date: '2026-11-01', inGross: 26.640, outGross: 26.380, pieces: 10, status: 'Done' },
  { id: 'P-913', jobId: 'J-1175', stage: 'QC', partyId: 'K-05', date: '2026-11-06', inGross: 26.380, outGross: 26.200, pieces: 10, status: 'Done' },
  { id: 'P-921', jobId: 'J-1182', stage: 'Alloying', partyId: 'K-07', date: '2026-11-02', inGross: 30.151, outGross: 32.880, pieces: 0, status: 'Done' },
  { id: 'P-922', jobId: 'J-1182', stage: 'Casting', partyId: 'K-07', date: '2026-11-04', inGross: 32.880, outGross: 32.410, pieces: 6, status: 'Done' },
  { id: 'P-923', jobId: 'J-1182', stage: 'Filing', partyId: 'K-07', date: '2026-11-05', inGross: 32.410, outGross: 31.900, pieces: 6, status: 'Done' },
  { id: 'P-924', jobId: 'J-1182', stage: 'Polishing', partyId: 'K-07', date: '2026-11-07', inGross: 31.900, outGross: 31.420, pieces: 6, status: 'Done' },
  { id: 'P-925', jobId: 'J-1182', stage: 'QC', partyId: 'K-07', date: '2026-11-11', inGross: 31.420, outGross: 31.284, pieces: 6, status: 'Done' },
  { id: 'P-931', jobId: 'J-1168', stage: 'Alloying', partyId: 'K-03', date: '2026-11-05', inGross: 25.126, outGross: 27.293, pieces: 0, status: 'Done' },
  { id: 'P-932', jobId: 'J-1168', stage: 'Casting', partyId: 'S-01', date: '2026-11-06', inGross: 20.0, outGross: 19.820, pieces: 2, status: 'Done' },
  { id: 'P-933', jobId: 'J-1168', stage: 'Casting', partyId: 'K-03', date: '2026-11-07', inGross: 27.293, outGross: 26.950, pieces: 2, status: 'Done' },
  { id: 'P-934', jobId: 'J-1168', stage: 'Setting', partyId: 'K-05', date: '2026-11-10', inGross: 12.0, outGross: 0, pieces: 1, status: 'In progress', note: 'Ruby setting on kada #1' },
  { id: 'P-941', jobId: 'J-1190', stage: 'Alloying', partyId: 'K-08', date: '2026-11-06', inGross: 40.0, outGross: 43.450, pieces: 0, status: 'Done' },
  { id: 'P-942', jobId: 'J-1190', stage: 'Filing', partyId: 'K-08', date: '2026-11-09', inGross: 43.450, outGross: 38.120, pieces: 2, status: 'Done', note: 'Link forming; 5.3 g WIP set aside' },
  { id: 'P-943', jobId: 'J-1190', stage: 'Polishing', partyId: 'K-08', date: '2026-11-11', inGross: 28.120, outGross: 0, pieces: 1, status: 'In progress' },
  { id: 'P-951', jobId: 'J-1191', stage: 'Casting', partyId: 'S-03', date: '2026-11-11', inGross: 15.075, outGross: 0, pieces: 15, status: 'In progress', note: 'Die-striking' },
];

export const RETURNS: ReturnEntry[] = [
  { id: 'R-7060', jobId: 'J-1160', from: 'K-03', type: 'Finished goods', gross: 42.900, declaredFineness: 0.916, pieces: 24, date: '2026-10-30', partial: false },
  { id: 'R-7061', jobId: 'J-1160', from: 'K-03', type: 'Dust & sweep', gross: 0.950, declaredFineness: 0.4, assayedFineness: 0.38, pieces: 0, date: '2026-10-30', partial: false },
  { id: 'R-7088', jobId: 'J-1175', from: 'K-05', type: 'Finished goods', gross: 26.200, declaredFineness: 0.75, pieces: 10, date: '2026-11-06', partial: false },
  { id: 'R-7089', jobId: 'J-1175', from: 'K-05', type: 'Scrap', gross: 0.180, declaredFineness: 0.75, assayedFineness: 0.75, pieces: 0, date: '2026-11-06', partial: false },
  { id: 'R-7101', jobId: 'J-1182', from: 'K-07', type: 'Scrap', gross: 1.040, declaredFineness: 0.916, assayedFineness: 0.75, pieces: 0, date: '2026-11-08', partial: true },
  { id: 'R-7105', jobId: 'J-1182', from: 'K-07', type: 'Finished goods', gross: 31.284, declaredFineness: 0.916, pieces: 6, date: '2026-11-12', partial: false },
  { id: 'R-7110', jobId: 'J-1190', from: 'K-08', type: 'Finished goods', gross: 28.0, declaredFineness: 0.916, pieces: 1, date: '2026-11-10', partial: true },
  { id: 'R-7111', jobId: 'J-1190', from: 'K-08', type: 'WIP', gross: 10.0, declaredFineness: 0.916, pieces: 0, date: '2026-11-10', partial: true },
];

export const EVIDENCE: EvidenceDoc[] = [
  { id: 'AR-3307', jobId: 'J-1182', kind: 'Assay report', title: 'Assay AR-3307 — scrap lot R-7101', detail: 'XRF + fire assay: 75.0% Au (declared 91.6%).', date: '2026-11-09' },
  { id: 'WS-8821', jobId: 'J-1182', kind: 'Weighing slip', title: 'Weighing slip WS-8821 — final return', detail: '31.284 g gross on Scale 4, photo attached.', date: '2026-11-12' },
  { id: 'CAL-04', jobId: 'J-1182', kind: 'Calibration log', title: 'Scale 4 calibration log', detail: 'Drift +0.03 g recorded since 01 Nov check.', date: '2026-11-11' },
  { id: 'ACK-3301', jobId: 'J-1182', kind: 'Acknowledgement', title: 'Lot L-3301 acknowledgement', detail: 'Signed by head karigar on receipt.', date: '2026-11-02' },
  { id: 'AR-3290', jobId: 'J-1175', kind: 'Assay report', title: 'Assay AR-3290 — scrap lot R-7089', detail: 'Fire assay: 75.0% Au, matches declaration.', date: '2026-11-07' },
  { id: 'WS-8790', jobId: 'J-1175', kind: 'Weighing slip', title: 'Weighing slip WS-8790 — final return', detail: '26.200 g gross on Scale 2.', date: '2026-11-06' },
  { id: 'AR-3255', jobId: 'J-1160', kind: 'Assay report', title: 'Assay AR-3255 — dust & sweep', detail: 'Fire assay: 38.0% Au (declared 40%).', date: '2026-10-31' },
];

export const SETTLEMENT_STATUS: Record<string, SettlementStatus> = {
  'J-1160': 'Approved',
  'J-1175': 'Pending approval',
  'J-1182': 'On hold',
  'J-1190': 'Draft',
};

export const AUDIT_SEED: AuditEntry[] = [
  { id: 'A-55060', at: '2026-10-21T10:12', actor: 'Vault desk', action: 'Issued lot L-3279 (40.201 g @ 99.5%)', target: 'J-1160', source: 'seed' },
  { id: 'A-55071', at: '2026-10-31T16:40', actor: 'Assay desk', action: 'Recorded assay AR-3255 (dust 38.0%)', target: 'J-1160', source: 'seed' },
  { id: 'A-55074', at: '2026-11-01T11:05', actor: 'Production manager', action: 'Approved settlement for J-1160', target: 'J-1160', source: 'seed' },
  { id: 'A-55080', at: '2026-11-02T09:58', actor: 'Vault desk', action: 'Issued lot L-3301 (30.151 g @ 99.5%)', target: 'J-1182', source: 'seed' },
  { id: 'A-55081', at: '2026-11-02T14:20', actor: 'Farida Shaikh', action: 'Transferred 30.151 g to Anil Verma (T-5101)', target: 'J-1182', source: 'seed' },
  { id: 'A-55090', at: '2026-11-05T12:30', actor: 'Mahesh Soni', action: 'Split J-1168 into batches A/B (T-5104, T-5105)', target: 'J-1168', source: 'seed' },
  { id: 'A-55096', at: '2026-11-09T10:15', actor: 'Assay desk', action: 'Recorded assay AR-3307 (scrap 75.0% vs declared 91.6%)', target: 'J-1182', source: 'seed' },
  { id: 'A-55098', at: '2026-11-09T15:02', actor: 'Vault desk', action: 'Issued lot L-3310 (25.126 g) — acknowledgement pending', target: 'J-1186', source: 'seed' },
  { id: 'A-55101', at: '2026-11-12T10:42', actor: 'Vault desk', action: 'Received final return R-7105 (31.284 g @ 91.6%)', target: 'J-1182', source: 'seed' },
  { id: 'A-55102', at: '2026-11-12T10:45', actor: 'Reconciliation engine', action: 'Flagged variance 0.204 g beyond allowance', target: 'J-1182', source: 'seed' },
];
