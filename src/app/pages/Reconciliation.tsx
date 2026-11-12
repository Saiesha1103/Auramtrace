import { useMemo, useState } from 'react';
import { useAppState } from '../data/store';
import { fine, g3, pct, r3, reconcile, returnFine, type JobRecon } from '../data/calc';
import type { Job } from '../data/types';
import { navigate } from '../router';
import { Btn, Card, DataTable, Empty, Field, FormGrid, Kpi, PageHeader, Pill, SelectFilter, Toolbar, statusTone } from '../ui';

const SEG = [
  { key: 'fg', label: 'Finished goods', color: '#e6c278' },
  { key: 'scrap', label: 'Scrap', color: '#c48a32' },
  { key: 'dust', label: 'Dust & sweep', color: '#8b5a22' },
  { key: 'wip', label: 'WIP returned', color: '#a9874f' },
  { key: 'out', label: 'Still in custody', color: 'repeating-linear-gradient(135deg, rgba(244,236,220,0.28) 0 4px, rgba(244,236,220,0.08) 4px 8px)' },
  { key: 'allow', label: 'Loss within allowance', color: 'rgba(244,236,220,0.35)' },
  { key: 'unexp', label: 'Unexplained variance', color: '#e8845a' },
] as const;

export function Reconciliation({ id }: { id?: string }) {
  const s = useAppState();
  const [status, setStatus] = useState('All');
  const rows = useMemo(() => s.jobs.map((j) => ({ j, rec: reconcile(s, j) })).filter((r) => r.rec.status !== 'Not issued'), [s]);
  const shown = rows.filter((r) => status === 'All' || r.rec.status === status);
  const selected = rows.find((r) => r.j.id === id) ?? rows.find((r) => r.rec.status === 'Exception') ?? rows[0];
  const totals = {
    issued: r3(rows.reduce((a, r) => a + r.rec.issuedFine, 0)),
    returned: r3(rows.reduce((a, r) => a + r.rec.returnedFine, 0)),
    unexplained: r3(rows.reduce((a, r) => a + r.rec.unexplainedFine, 0)),
  };

  return (
    <div className="stack">
      <PageHeader eyebrow="Control" title="Reconciliation" lede="Fine-gold material balance per job: issued against everything returned, process-loss allowance and unexplained variance." />
      <div className="kpis">
        <Kpi icon="issue" label="Fine issued (all jobs)" value={g3(totals.issued)} />
        <Kpi icon="return" label="Fine returned" value={g3(totals.returned)} />
        <Kpi icon="layers" label="Still in custody" value={g3(r3(totals.issued - totals.returned))} />
        <Kpi icon="alert" label="Unexplained variance" value={g3(totals.unexplained)} tone={totals.unexplained > 0 ? 'alert' : undefined} />
      </div>
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SelectFilter label="Status" value={status} onChange={setStatus} options={['All', 'Open', 'Within tolerance', 'Exception']} />
          </Toolbar>
        </div>
        <DataTable
          caption="Reconciliation by job"
          rows={shown}
          rowKey={(r) => r.j.id}
          onRowClick={(r) => navigate('reconciliation', r.j.id)}
          initialSort={{ key: 'unexp', dir: 'desc' }}
          columns={[
            { key: 'job', header: 'Job', sort: (r) => r.j.id, render: (r) => <span className="cell-main"><b>{r.j.title}</b><small className="mono">{r.j.id}{selected?.j.id === r.j.id ? ' · selected' : ''}</small></span> },
            { key: 'iss', header: 'Issued', align: 'right', render: (r) => <span className="mono">{g3(r.rec.issuedFine)}</span> },
            { key: 'ret', header: 'Returned', align: 'right', render: (r) => <span className="mono">{g3(r.rec.returnedFine)}</span> },
            { key: 'allow', header: 'Allowance', align: 'right', hideSm: true, render: (r) => <span className="mono">{g3(r.rec.allowanceFine)}</span> },
            { key: 'var', header: 'Variance', align: 'right', hideSm: true, render: (r) => <span className="mono">{r.rec.closed ? g3(r.rec.varianceFine) : 'open'}</span> },
            { key: 'unexp', header: 'Unexplained', align: 'right', sort: (r) => r.rec.unexplainedFine, render: (r) => <span className={`mono ${r.rec.unexplainedFine ? 'alert-text' : ''}`}>{r.rec.closed ? g3(r.rec.unexplainedFine) : '—'}</span> },
            { key: 'st', header: 'Status', sort: (r) => r.rec.status, render: (r) => <Pill tone={statusTone(r.rec.status)}>{r.rec.status}</Pill> },
          ]}
        />
      </Card>
      {selected ? <Detail job={selected.j} rec={selected.rec} /> : <Empty title="No issued jobs to reconcile" />}
      <FineCalculator />
    </div>
  );
}

function Detail({ job, rec }: { job: Job; rec: JobRecon }) {
  const s = useAppState();
  const rets = s.returns.filter((r) => r.jobId === job.id);
  const lots = s.lots.filter((l) => l.jobId === job.id);
  const lossWithin = rec.closed ? r3(Math.min(rec.varianceFine, rec.allowanceFine)) : 0;
  const values: Record<(typeof SEG)[number]['key'], number> = {
    fg: rec.returnedByType['Finished goods'],
    scrap: rec.returnedByType.Scrap,
    dust: rec.returnedByType['Dust & sweep'],
    wip: rec.returnedByType.WIP,
    out: rec.closed ? 0 : rec.outstandingFine,
    allow: lossWithin,
    unexp: rec.unexplainedFine,
  };
  const segs = SEG.filter((x) => values[x.key] > 0);

  return (
    <div className="grid-2">
      <Card
        title={`Material balance · ${job.id} ${job.title}`}
        actions={
          <>
            <Pill tone={statusTone(rec.status)}>{rec.status}</Pill>
            {rec.status === 'Exception' && <Btn size="sm" icon="sparkle" onClick={() => navigate('investigation', `EX-${job.id.slice(2)}-V`)}>Investigate</Btn>}
          </>
        }
      >
        <div className="balance">
          <div className="balance-bar" role="img" aria-label={`Issued ${g3(rec.issuedFine)} fine broken into ${segs.map((x) => `${x.label} ${g3(values[x.key])}`).join(', ')}`}>
            {segs.map((x) => (
              <span key={x.key} style={{ width: `${(values[x.key] / Math.max(rec.issuedFine, 0.001)) * 100}%`, background: x.color }} />
            ))}
          </div>
          <div className="balance-legend">
            {segs.map((x) => (
              <span key={x.key}>
                <i style={{ background: x.color }} />
                {x.label} <b className="mono">{g3(values[x.key])}</b>
              </span>
            ))}
          </div>
        </div>
        <div className="formula" style={{ marginTop: 16 }}>
          {lots.map((l) => `Issued   ${l.id}  ${l.gross.toFixed(3)} g × ${pct(l.fineness)} = ${fine(l.gross, l.fineness).toFixed(3)} g\n`).join('')}
          {rets.map((r) => `Returned ${r.id}  ${r.gross.toFixed(3)} g × ${pct(r.assayedFineness ?? r.declaredFineness)}${r.assayedFineness !== undefined ? ' (assay)' : ''} = ${returnFine(r).toFixed(3)} g\n`).join('')}
          {'\n'}
          <b>Variance</b>    = {rec.issuedFine.toFixed(3)} − {rec.returnedFine.toFixed(3)} = <b>{rec.outstandingFine.toFixed(3)} g</b>
          {rec.closed ? '' : '  (job open — not yet a variance)'}
          {'\n'}
          <b>Allowance</b>   = {rec.issuedFine.toFixed(3)} × {job.lossAllowancePct}% = <b>{rec.allowanceFine.toFixed(3)} g</b>
          {'\n'}
          <b>Unexplained</b> = max(0, variance − allowance) = <b>{rec.closed ? rec.unexplainedFine.toFixed(3) : '—'} g</b>
        </div>
      </Card>
      <Card title="Checks">
        <ul className="rule-list">
          <li>
            <span aria-hidden="true">{rec.closed ? '✓' : '•'}</span>
            <span>{rec.closed ? 'Final return received — job closed for reconciliation.' : 'Job still open: variance is not assessed until the final return.'}</span>
            <span />
          </li>
          <li>
            <span aria-hidden="true">{lots.every((l) => l.acknowledged) ? '✓' : '!'}</span>
            <span>{lots.every((l) => l.acknowledged) ? 'All issued lots acknowledged.' : 'One or more issued lots are not acknowledged.'}</span>
            <span />
          </li>
          <li>
            <span aria-hidden="true">{rec.purityShortfallFine > 0 ? '!' : '✓'}</span>
            <span>{rec.purityShortfallFine > 0 ? 'Assay found purity below declaration on a return.' : 'No purity shortfalls at assay.'}</span>
            <b>{rec.purityShortfallFine > 0 ? g3(rec.purityShortfallFine) : ''}</b>
          </li>
          <li>
            <span aria-hidden="true">{rets.some((r) => r.assayedFineness === undefined && r.type !== 'Finished goods') ? '!' : '✓'}</span>
            <span>{rets.some((r) => r.assayedFineness === undefined && r.type !== 'Finished goods') ? 'Some scrap / dust / WIP is not assayed yet — declared purity used.' : 'All non-finished returns assayed.'}</span>
            <span />
          </li>
        </ul>
      </Card>
    </div>
  );
}

function FineCalculator() {
  const [gross, setGross] = useState('10');
  const [karat, setKarat] = useState('22');
  const fn = Math.min(0.9999, (Number(karat) || 0) / 24);
  const [custom, setCustom] = useState('');
  const used = custom ? Number(custom) : fn;
  return (
    <Card title="Fine-gold calculator">
      <FormGrid>
        <Field label="Gross weight (g)">
          <input type="number" min={0} step={0.001} value={gross} onChange={(e) => setGross(e.target.value)} />
        </Field>
        <Field label="Karat" hint={`= ${pct(fn)} (karat ÷ 24)`}>
          <select value={karat} onChange={(e) => { setKarat(e.target.value); setCustom(''); }}>
            {['24', '22', '20', '18', '14'].map((k) => (
              <option key={k} value={k}>{k}K</option>
            ))}
          </select>
        </Field>
        <Field label="Or exact fineness" hint="Overrides karat, e.g. 0.916 or 0.995">
          <input type="number" min={0} max={0.9999} step={0.001} value={custom} onChange={(e) => setCustom(e.target.value)} />
        </Field>
      </FormGrid>
      <p className="calc-preview" style={{ marginTop: 14 }}>
        Fine gold = {Number(gross || 0).toFixed(3)} g × {pct(used || 0)} = <b>{g3(fine(Number(gross) || 0, used || 0))}</b>
      </p>
    </Card>
  );
}
