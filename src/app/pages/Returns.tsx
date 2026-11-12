import { useMemo, useState } from 'react';
import { recordReturn, useAppState } from '../data/store';
import { AS_OF } from '../data/seed';
import { custody, fine, fmtDate, g3, pct, r3, returnFine } from '../data/calc';
import type { ReturnEntry, ReturnType } from '../data/types';
import { useLookups } from '../lookups';
import { Link, useRoute } from '../router';
import { Btn, Card, DataTable, DemoNote, Dialog, Field, FormGrid, FormMessage, Kpi, PageHeader, Pill, SelectFilter, Toolbar } from '../ui';

const TYPES: ReturnType[] = ['Finished goods', 'Scrap', 'Dust & sweep', 'WIP'];
const TYPE_ICON = { 'Finished goods': 'return', Scrap: 'scale', 'Dust & sweep': 'flame', WIP: 'manufacture' } as const;

export function Returns() {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const { query } = useRoute();
  const [type, setType] = useState('All types');
  const [jobId, setJobId] = useState(query.get('job') ?? 'All jobs');
  const [partial, setPartial] = useState('All');
  const [open, setOpen] = useState(false);

  const rows = s.returns.filter((r) => (type === 'All types' || r.type === type) && (jobId === 'All jobs' || r.jobId === jobId) && (partial === 'All' || (partial === 'Partial') === r.partial));
  const byType = useMemo(() => Object.fromEntries(TYPES.map((t) => [t, r3(s.returns.filter((r) => r.type === t).reduce((a, r) => a + returnFine(r), 0))])) as Record<ReturnType, number>, [s.returns]);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Custody · step 4"
        title="Returns"
        lede="Gold coming back to the vault — finished goods, scrap, dust & sweep and unfinished WIP, in full or in part."
        actions={<Btn variant="gold" icon="return" onClick={() => setOpen(true)}>Record return</Btn>}
      />
      <div className="kpis">
        {TYPES.map((t) => (
          <Kpi key={t} icon={TYPE_ICON[t]} label={t} value={g3(byType[t])} sub="fine returned" />
        ))}
      </div>
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SelectFilter label="Type" value={type} onChange={setType} options={['All types', ...TYPES]} />
            <SelectFilter label="Job" value={jobId} onChange={setJobId} options={['All jobs', ...s.jobs.map((j) => ({ value: j.id, label: `${j.id} · ${j.title}` }))]} />
            <SelectFilter label="Completeness" value={partial} onChange={setPartial} options={['All', 'Partial', 'Final']} />
          </Toolbar>
        </div>
        <DataTable<ReturnEntry>
          caption="Returns register"
          rows={rows}
          rowKey={(r) => r.id}
          initialSort={{ key: 'date', dir: 'desc' }}
          columns={[
            { key: 'id', header: 'Return', sort: (r) => r.id, render: (r) => <span className="cell-main"><b className="mono">{r.id}</b><small>{fmtDate(r.date)}</small></span> },
            { key: 'job', header: 'Job', hideSm: true, render: (r) => <Link to="jobs" id={r.jobId} className="link">{jobLabel(r.jobId)}</Link> },
            { key: 'from', header: 'From', render: (r) => partyName(r.from) },
            { key: 'type', header: 'Type', sort: (r) => r.type, render: (r) => <span className="row-actions" style={{ justifyContent: 'flex-start' }}>{r.type}{r.partial ? <Pill tone="warn" icon={null}>Partial</Pill> : <Pill tone="muted" icon={null}>Final</Pill>}</span> },
            { key: 'pcs', header: 'Pcs', align: 'right', hideSm: true, render: (r) => r.pieces || '—' },
            { key: 'gross', header: 'Gross', align: 'right', sort: (r) => r.gross, render: (r) => <span className="mono">{g3(r.gross)}</span> },
            {
              key: 'purity',
              header: 'Purity',
              align: 'right',
              render: (r) =>
                r.assayedFineness === undefined ? (
                  <span className="mono muted" title="Not assayed — declared purity used">{pct(r.declaredFineness)} decl.</span>
                ) : r.assayedFineness < r.declaredFineness - 0.02 ? (
                  <span className="mono alert-text" title={`Declared ${pct(r.declaredFineness)}`}>{pct(r.assayedFineness)} assay ⚠</span>
                ) : (
                  <span className="mono">{pct(r.assayedFineness)} assay</span>
                ),
            },
            { key: 'fine', header: 'Fine', align: 'right', sort: (r) => returnFine(r), render: (r) => <span className="mono gold">{g3(returnFine(r))}</span> },
          ]}
        />
      </Card>
      <ReturnDialog key={jobId} open={open} onClose={() => setOpen(false)} initialJob={jobId === 'All jobs' ? 'J-1168' : jobId} />
    </div>
  );
}

function ReturnDialog({ open, onClose, initialJob }: { open: boolean; onClose: () => void; initialJob: string }) {
  const s = useAppState();
  const { partyName } = useLookups();
  const [jobId, setJobId] = useState(initialJob);
  const holders = useMemo(() => [...custody(s, jobId).entries()].filter(([, v]) => v > 0.0005), [s, jobId]);
  const job = s.jobs.find((j) => j.id === jobId);
  const [f, setF] = useState({ from: '', type: 'Finished goods' as ReturnType, gross: '', fineness: '', pieces: '0', partial: true });
  const from = f.from || holders[0]?.[0] || '';
  const fn = Number(f.fineness || job?.fineness || 0);
  const g = Number(f.gross) || 0;
  const held = custody(s, jobId).get(from) ?? 0;
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const submit = () => {
    if (!from) return setMsg({ ok: false, text: 'Nobody holds gold on this job.' });
    const res = recordReturn({ jobId, from, type: f.type, gross: g, declaredFineness: fn, pieces: Number(f.pieces) || 0, date: AS_OF, partial: f.partial });
    setMsg(res.ok ? { ok: true, text: `Recorded ${res.id} in this browser session only — not saved to any server. Purity is as declared until assayed.` } : { ok: false, text: res.error });
  };
  const close = () => {
    setMsg(null);
    onClose();
  };
  return (
    <Dialog
      open={open}
      title="Record return"
      onClose={close}
      footer={
        <>
          <Btn onClick={close}>Close</Btn>
          <Btn variant="gold" icon="return" onClick={submit}>Record return (local demo)</Btn>
        </>
      }
    >
      <DemoNote>No API is connected. Returns are checked against the holder’s custody on the job and kept in this browser session only.</DemoNote>
      <FormGrid>
        <Field label="Job">
          <select value={jobId} onChange={(e) => { setJobId(e.target.value); setF({ ...f, from: '', fineness: '' }); }}>
            {s.jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.id} · {j.title}</option>
            ))}
          </select>
        </Field>
        <Field label="Returned by" hint={from ? `Holds ${g3(held)} fine on this job` : 'No holders on this job'}>
          <select value={from} onChange={(e) => setF({ ...f, from: e.target.value })}>
            {holders.map(([id]) => (
              <option key={id} value={id}>{partyName(id)}</option>
            ))}
          </select>
        </Field>
        <Field label="Type">
          <select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value as ReturnType })}>
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="Gross weight (g)">
          <input type="number" min={0} step={0.001} value={f.gross} onChange={(e) => setF({ ...f, gross: e.target.value })} />
        </Field>
        <Field label="Declared purity" hint={`Job is ${job?.karat ?? '—'}; leave blank to use ${pct(job?.fineness ?? 0)}`}>
          <input type="number" min={0} max={0.9999} step={0.001} value={f.fineness} placeholder={String(job?.fineness ?? '')} onChange={(e) => setF({ ...f, fineness: e.target.value })} />
        </Field>
        <Field label="Pieces">
          <input type="number" min={0} step={1} value={f.pieces} onChange={(e) => setF({ ...f, pieces: e.target.value })} />
        </Field>
        <label className="check-row field-wide">
          <input type="checkbox" checked={f.partial} onChange={(e) => setF({ ...f, partial: e.target.checked })} />
          Partial return — more gold is still expected on this job (untick for the final return, which closes the job for reconciliation)
        </label>
      </FormGrid>
      <p className="calc-preview">
        Fine returned: <b>{g3(fine(g, fn))}</b> · holder keeps <b>{g3(r3(held - fine(g, fn)))}</b>
      </p>
      <FormMessage result={msg} />
    </Dialog>
  );
}
