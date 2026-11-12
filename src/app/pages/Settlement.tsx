import { useMemo, useState } from 'react';
import { setSettlement, useAppState } from '../data/store';
import { GOLD_RATE_PER_FINE_G, exceptions, g3, inr, reconcile, settlementFor, type SettlementLine } from '../data/calc';
import type { SettlementStatus } from '../data/types';
import { useLookups } from '../lookups';
import { Link, navigate } from '../router';
import { Btn, Card, DataTable, DemoNote, FormMessage, Kpi, PageHeader, Pill, SelectFilter, Toolbar, statusTone } from '../ui';

interface Row extends SettlementLine {
  status: SettlementStatus;
  closed: boolean;
  blockers: string[];
}

export function Settlement({ id }: { id?: string }) {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const [status, setStatus] = useState('All');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const rows: Row[] = useMemo(() => {
    const ex = exceptions(s);
    return s.jobs
      .map((j) => {
        const line = settlementFor(s, j);
        if (!line) return null;
        const rec = reconcile(s, j);
        const blockers: string[] = [];
        if (!rec.closed) blockers.push('Final return not received');
        ex.filter((e) => e.jobId === j.id && (e.kind === 'Variance' || e.kind === 'Purity mismatch') && s.exceptionReview[e.id] !== 'Resolved').forEach((e) => blockers.push(`${e.id} unresolved`));
        return { ...line, status: s.settlement[j.id] ?? 'Draft', closed: rec.closed, blockers } as Row;
      })
      .filter((r): r is Row => r !== null);
  }, [s]);
  const shown = rows.filter((r) => status === 'All' || r.status === status);
  const selected = rows.find((r) => r.jobId === id);

  const act = (r: Row, next: SettlementStatus) => {
    if (next === 'Approved' && r.blockers.length) return setMsg({ ok: false, text: `Cannot approve ${r.jobId}: ${r.blockers.join('; ')}.` });
    setSettlement(r.jobId, next);
    setMsg({ ok: true, text: `${r.jobId} set to “${next}” in this browser session only (local demo — no server approval was recorded).` });
  };

  const sum = (k: keyof SettlementLine) => rows.reduce((a, r) => a + (r[k] as number), 0);

  return (
    <div className="stack">
      <PageHeader eyebrow="Control" title="Settlement" lede="Labour payable, wastage against allowance, gold still outstanding and the approval trail for each job." />
      <div className="kpis">
        <Kpi icon="shield" label="Labour (all returned jobs)" value={inr(sum('labour'))} />
        <Kpi icon="scale" label="Excess wastage" value={g3(sum('excessFine'))} sub={`recoverable ${inr(sum('recovery'))}`} tone={sum('excessFine') > 0 ? 'alert' : undefined} />
        <Kpi icon="layers" label="Gold outstanding" value={g3(sum('outstandingFine'))} sub="on returned jobs" />
        <Kpi icon="clock" label="Awaiting approval" value={rows.filter((r) => r.status === 'Pending approval').length} tone="warn" />
      </div>
      <DemoNote>
        Labour = finished-goods gross × the karigar’s ₹/g rate. Excess wastage = max(0, variance − allowance), valued at a synthetic reference rate of {inr(GOLD_RATE_PER_FINE_G)} per fine gram. Approvals here are local to this browser session.
      </DemoNote>
      <FormMessage result={msg} />
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SelectFilter label="Status" value={status} onChange={setStatus} options={['All', 'Draft', 'Pending approval', 'Approved', 'On hold']} />
          </Toolbar>
        </div>
        <DataTable<Row>
          caption="Settlements"
          rows={shown}
          rowKey={(r) => r.jobId}
          onRowClick={(r) => navigate('settlement', r.jobId)}
          columns={[
            { key: 'job', header: 'Job', sort: (r) => r.jobId, render: (r) => <span className="cell-main"><b>{jobLabel(r.jobId)}</b><small>{partyName(r.partyId)}</small></span> },
            { key: 'labour', header: 'Labour', align: 'right', sort: (r) => r.labour, render: (r) => <span className="mono">{inr(r.labour)}</span> },
            { key: 'allow', header: 'Allowance', align: 'right', hideSm: true, render: (r) => <span className="mono">{g3(r.allowanceFine)}</span> },
            { key: 'var', header: 'Wastage', align: 'right', hideSm: true, render: (r) => <span className="mono">{r.closed ? g3(r.varianceFine) : 'open'}</span> },
            { key: 'excess', header: 'Excess', align: 'right', render: (r) => <span className={`mono ${r.excessFine ? 'alert-text' : ''}`}>{g3(r.excessFine)}</span> },
            { key: 'out', header: 'Outstanding', align: 'right', hideSm: true, render: (r) => <span className="mono">{g3(r.outstandingFine)}</span> },
            { key: 'net', header: 'Net payable', align: 'right', sort: (r) => r.net, render: (r) => <span className="mono gold">{inr(r.net)}</span> },
            { key: 'st', header: 'Status', sort: (r) => r.status, render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
          ]}
        />
      </Card>

      {selected ? (
        <Card title={`Settlement · ${jobLabel(selected.jobId)}`} actions={<Link to="jobs" id={selected.jobId} className="link">Open job</Link>}>
          <div className="formula">
            Labour      = {selected.finishedGross.toFixed(3)} g × {inr(s.parties.find((p) => p.id === selected.partyId)?.labourRate ?? 0)}/g = <b>{inr(selected.labour)}</b>
            {'\n'}Excess      = max(0, {selected.varianceFine.toFixed(3)} − {selected.allowanceFine.toFixed(3)}) = <b>{selected.excessFine.toFixed(3)} g</b>
            {'\n'}Recovery    = {selected.excessFine.toFixed(3)} g × {inr(GOLD_RATE_PER_FINE_G)} = <b>{inr(selected.recovery)}</b>
            {'\n'}Net payable = {inr(selected.labour)} − {inr(selected.recovery)} = <b>{inr(selected.net)}</b>
            {'\n'}Outstanding gold with {partyName(selected.partyId)} on this job: <b>{selected.outstandingFine.toFixed(3)} g fine</b>
          </div>
          {selected.blockers.length > 0 && (
            <p className="form-msg is-err" style={{ marginTop: 12 }}>
              Approval blocked: {selected.blockers.join('; ')}.
            </p>
          )}
          <div className="row-actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap', marginTop: 14 }}>
            <Btn icon="arrow" onClick={() => act(selected, 'Pending approval')} disabled={selected.status === 'Pending approval' || selected.status === 'Approved'}>Submit for approval</Btn>
            <Btn variant="gold" icon="check" onClick={() => act(selected, 'Approved')} disabled={selected.status === 'Approved'}>Approve</Btn>
            <Btn variant="quiet" onClick={() => act(selected, 'On hold')} disabled={selected.status === 'On hold'}>Put on hold</Btn>
          </div>
        </Card>
      ) : (
        <p className="muted">Select a job above to see its settlement workings and approval actions.</p>
      )}
    </div>
  );
}

