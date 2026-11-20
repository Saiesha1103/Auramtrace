import { useCallback, useEffect, useState } from 'react';
import { portalApi, type TrackRecord, type WorksheetDto } from '../data/api';
import { Btn, Card, DataTable, Empty, FormMessage, Kpi, PageHeader, Pill, type Tone } from '../ui';

const inr = (n: number) => `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const g = (n: number | null | undefined) => (n == null ? '—' : `${n.toFixed(3)} g`);
const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');

const SHEET_TONE: Record<WorksheetDto['status'], Tone> = {
  draft: 'muted',
  submitted: 'muted',
  approved: 'warn',
  karigar_accepted: 'gold',
  disputed: 'alert',
  paid: 'ok',
  rejected: 'muted',
};
const SHEET_LABEL: Record<WorksheetDto['status'], string> = {
  draft: 'Draft',
  submitted: 'With jeweller',
  approved: 'Needs your answer',
  karigar_accepted: 'Agreed · awaiting payment',
  disputed: 'You disputed',
  paid: 'Paid',
  rejected: 'Withdrawn',
};

/** Karigar's own account: what they hold, what they're owed, and their record. Nothing about anyone else. */
export function Portal() {
  const [me, setMe] = useState<Awaited<ReturnType<typeof portalApi.me>> | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [ledger, setLedger] = useState<any[]>([]);
  const [sheets, setSheets] = useState<WorksheetDto[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [disputing, setDisputing] = useState<string | null>(null);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    try {
      const [m, j, l, s] = await Promise.all([portalApi.me(), portalApi.jobs(), portalApi.ledger(), portalApi.settlements()]);
      setMe(m);
      setJobs(j);
      setLedger(l);
      setSheets(s);
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      setMsg({ ok: true, text: ok });
      setDisputing(null);
      setReason('');
      await load();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
  };

  if (err) return <Card title="Could not load your account"><p className="muted">{err}</p></Card>;
  if (!me) return <p className="muted">Loading your account…</p>;

  const t: TrackRecord = me.trackRecord;
  const awaiting = sheets.filter((s) => s.status === 'approved');
  const unacked = ledger.filter((e) => (e.eventType === 'issue' || e.eventType === 'transfer') && e.to?.karigarId === me.karigar.id && !e.state?.acknowledged && !e.state?.reversed);

  return (
    <div className="stack">
      <PageHeader
        eyebrow={`Karigar account · ${me.karigar.code}`}
        title={`Namaste, ${me.karigar.name}`}
        lede="Your own gold ledger, settlements and record with this jeweller, read from the same records they see. You approve every settlement before it is final."
      />
      <FormMessage result={msg} />

      <div className="kpis">
        <Kpi label="Gold with you now" value={g(me.karigar.custody?.fineGoldG)} sub="fine gold, from the ledger" icon="scale" />
        <Kpi label="Waiting for your answer" value={awaiting.length} sub="settlements to accept or dispute" icon="shield" tone={awaiting.length ? 'warn' : undefined} />
        <Kpi label="On-time deliveries" value={t.onTimeRatePct == null ? '—' : `${t.onTimeRatePct}%`} sub={`${t.onTimeDeliveries} of ${t.jobsDelivered} delivered`} icon="clock" />
        <Kpi label="Avg. days to payment" value={t.averageDaysToPayment ?? '—'} sub={`${t.settlementsPaid} paid settlement(s)`} icon="check" />
      </div>

      <Card title="Settlements" actions={<Pill tone="gold" icon={null}>Two-party approval</Pill>}>
        {sheets.length ? (
          <ul className="list-plain portal-sheets">
            {sheets.map((s) => (
              <li key={s.id} className="portal-sheet">
                <div className="portal-sheet-head">
                  <b className="mono">{s.code}</b>
                  <Pill tone={SHEET_TONE[s.status]} icon={null}>{SHEET_LABEL[s.status]}</Pill>
                  <span className="portal-amount">{inr(s.netPayableAmount)}</span>
                </div>
                <p className="muted small">
                  Labour {inr(s.labourAmount)} · wastage allowed {g(s.wastageAllowanceFineG)} · actual loss {g(s.actualLossFineG)}
                  {s.excessLossFineG > 0 && <> · excess {g(s.excessLossFineG)} recovered {inr(s.goldRecoveryAmount)}</>}
                  {s.approvedDeductions > 0 && <> · deductions {inr(s.approvedDeductions)}</>}
                </p>
                {s.disputeReason && <p className="small">Your dispute: “{s.disputeReason}”</p>}
                {s.paidAt && <p className="small">Paid {day(s.paidAt)} · ref {s.paymentRef}</p>}
                {s.status === 'approved' && disputing !== s.id && (
                  <div className="row-actions" style={{ justifyContent: 'flex-start' }}>
                    <Btn variant="gold" icon="check" onClick={() => run(() => portalApi.accept(s.id), `You accepted ${s.code}. The jeweller can now pay it.`)}>Accept</Btn>
                    <Btn icon="alert" onClick={() => setDisputing(s.id)}>Dispute</Btn>
                  </div>
                )}
                {disputing === s.id && (
                  <div className="portal-dispute">
                    <label className="field field-wide">
                      <span className="field-label">What is wrong? (kept on the record for both sides)</span>
                      <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. My scale showed 39.800 g returned, not 39.500 g" />
                    </label>
                    <div className="row-actions" style={{ justifyContent: 'flex-start' }}>
                      <Btn variant="gold" disabled={reason.trim().length < 10} onClick={() => run(() => portalApi.dispute(s.id, reason.trim()), `Dispute recorded for ${s.code}.`)}>Send dispute</Btn>
                      <Btn variant="quiet" onClick={() => setDisputing(null)}>Cancel</Btn>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="No settlements yet" />
        )}
      </Card>

      {unacked.length > 0 && (
        <Card title="Confirm gold you received">
          <DataTable
            rows={unacked}
            rowKey={(e: any) => e.id}
            columns={[
              { key: 'date', header: 'Date', render: (e: any) => day(e.occurredAt) },
              { key: 'job', header: 'Job', render: (e: any) => e.jobCode ?? '—' },
              { key: 'w', header: 'Net weight', render: (e: any) => g(e.netWeightG), align: 'right' },
              { key: 'c', header: 'Challan', render: (e: any) => e.challanRef ?? '—' },
              { key: 'a', header: '', render: (e: any) => <Btn size="sm" icon="check" onClick={() => run(() => portalApi.acknowledge(e.id), 'Receipt confirmed and recorded.')}>I received this</Btn> },
            ]}
          />
        </Card>
      )}

      <div className="grid-2-even">
        <Card title="My jobs">
          {jobs.length ? (
            <ul className="list-plain">
              {jobs.map((j) => (
                <li key={j.id} className="doc-item">
                  <span>
                    <b className="mono">{j.code}</b> · {j.title}
                  </span>
                  <small>
                    Due {day(j.dueDate)}
                    {j.occasionDate && <> · {j.occasionLabel || 'Customer occasion'} {day(j.occasionDate)}</>} · {j.status.replace('_', ' ')}
                  </small>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No jobs yet" />
          )}
        </Card>
        <Card title="My record" actions={<Pill tone="muted" icon={null}>Derived, not self-reported</Pill>}>
          <ul className="rule-list">
            <li><span>Jobs delivered</span><b>{t.jobsDelivered} / {t.jobsTotal}</b></li>
            <li><span>Customer occasion dates kept</span><b>{t.occasionDatesKept} / {t.occasionJobsDelivered}</b></li>
            <li><span>Jobs within wastage allowance</span><b>{t.withinWastageAllowance} / {t.reconciledJobs}</b></li>
            <li><span>Settlements disputed</span><b>{t.settlementsDisputed}</b></li>
            <li><span>Open exceptions</span><b>{t.exceptionsOpen}</b></li>
          </ul>
          <p className="muted small">{t.basis}</p>
        </Card>
      </div>

      <Card title="My gold ledger">
        <DataTable
          rows={ledger}
          rowKey={(e: any) => e.id}
          columns={[
            { key: 'date', header: 'Date', render: (e: any) => day(e.occurredAt) },
            { key: 't', header: 'Movement', render: (e: any) => e.eventType.replace(/_/g, ' ') },
            { key: 'job', header: 'Job', render: (e: any) => e.jobCode ?? '—' },
            { key: 'w', header: 'Net', render: (e: any) => g(e.netWeightG), align: 'right' },
            { key: 'f', header: 'Fine', render: (e: any) => g(e.fineGoldG), align: 'right' },
            { key: 'c', header: 'Challan', render: (e: any) => e.challanRef ?? '—' },
          ]}
        />
      </Card>
    </div>
  );
}
