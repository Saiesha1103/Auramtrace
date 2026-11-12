import { useMemo, useState } from 'react';
import { addProduction, useAppState } from '../data/store';
import { AS_OF, VAULT } from '../data/seed';
import { fmtDate, g3, r3 } from '../data/calc';
import { STAGES, type ProductionEntry, type Stage } from '../data/types';
import { useLookups } from '../lookups';
import { Link, useRoute } from '../router';
import { Btn, Card, DataTable, DemoNote, Dialog, Field, FormGrid, FormMessage, Kpi, PageHeader, Pill, SelectFilter, Tabs, Toolbar, statusTone } from '../ui';

const lossOf = (p: ProductionEntry) => (p.status === 'Done' && p.stage !== 'Alloying' ? r3(p.inGross - p.outGross) : null);

export function Production() {
  const s = useAppState();
  const { partyName } = useLookups();
  const { query } = useRoute();
  const [tab, setTab] = useState<'board' | 'measurements' | 'output'>('board');
  const [jobId, setJobId] = useState(query.get('job') ?? 'All jobs');
  const [open, setOpen] = useState(false);
  const entries = s.production.filter((p) => jobId === 'All jobs' || p.jobId === jobId);
  const live = s.production.filter((p) => p.status === 'In progress');
  const done = s.production.filter((p) => lossOf(p) !== null);
  const totalLoss = r3(done.reduce((a, p) => a + (lossOf(p) ?? 0), 0));

  const output = useMemo(
    () =>
      s.jobs
        .filter((j) => s.production.some((p) => p.jobId === j.id))
        .map((j) => {
          const fg = s.returns.filter((r) => r.jobId === j.id && r.type === 'Finished goods');
          const fgGross = r3(fg.reduce((a, r) => a + r.gross, 0));
          const target = r3(j.pieces * j.targetGrossPerPiece);
          const pieces = fg.reduce((a, r) => a + r.pieces, 0);
          const lastStage = [...s.production.filter((p) => p.jobId === j.id)].sort((a, b) => a.date.localeCompare(b.date)).pop();
          return { j, fgGross, target, pieces, lastStage };
        }),
    [s],
  );

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Custody · step 3"
        title="Production"
        lede="Manufacturing stages with in/out measurements and finished output against target."
        actions={<Btn variant="gold" icon="plus" onClick={() => setOpen(true)}>Log stage</Btn>}
      />
      <div className="kpis">
        <Kpi icon="manufacture" label="Stages in progress" value={live.length} />
        <Kpi icon="check" label="Stages completed" value={s.production.length - live.length} />
        <Kpi icon="scale" label="Measured process loss" value={g3(totalLoss)} sub="gross, excl. alloying" />
      </div>
      <Toolbar>
        <Tabs label="Production views" value={tab} onChange={setTab} tabs={[{ key: 'board', label: 'Stage board' }, { key: 'measurements', label: 'Measurements', count: entries.length }, { key: 'output', label: 'Output' }]} />
        <SelectFilter label="Job" value={jobId} onChange={setJobId} options={['All jobs', ...s.jobs.map((j) => ({ value: j.id, label: `${j.id} · ${j.title}` }))]} />
      </Toolbar>

      {tab === 'board' && (
        <Card>
          <div className="board">
            {STAGES.map((stage) => {
              const col = entries.filter((p) => p.stage === stage);
              return (
                <div key={stage} className="board-col">
                  <h3>
                    {stage} <span className="mono">{col.length}</span>
                  </h3>
                  {col.map((p) => (
                    <div key={p.id} className={`board-card ${p.status === 'In progress' ? 'is-live' : ''}`}>
                      <Link to="jobs" id={p.jobId} className="link mono">{p.jobId}</Link>
                      <b>{partyName(p.partyId)}</b>
                      <small>
                        {fmtDate(p.date)} · in {p.inGross.toFixed(3)} g{p.status === 'Done' ? ` · out ${p.outGross.toFixed(3)} g` : ''}
                      </small>
                      <Pill tone={statusTone(p.status)}>{p.status}</Pill>
                    </div>
                  ))}
                  {col.length === 0 && <small className="muted">—</small>}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {tab === 'measurements' && (
        <Card pad={false}>
          <DataTable<ProductionEntry>
            caption="Production measurements"
            rows={entries}
            rowKey={(r) => r.id}
            initialSort={{ key: 'date', dir: 'desc' }}
            columns={[
              { key: 'date', header: 'Date', sort: (r) => r.date, render: (r) => fmtDate(r.date) },
              { key: 'job', header: 'Job', sort: (r) => r.jobId, render: (r) => <Link to="jobs" id={r.jobId} className="link mono">{r.jobId}</Link> },
              { key: 'stage', header: 'Stage', sort: (r) => STAGES.indexOf(r.stage), render: (r) => r.stage },
              { key: 'by', header: 'By', hideSm: true, render: (r) => partyName(r.partyId) },
              { key: 'in', header: 'In (g)', align: 'right', render: (r) => <span className="mono">{r.inGross.toFixed(3)}</span> },
              { key: 'out', header: 'Out (g)', align: 'right', render: (r) => <span className="mono">{r.status === 'Done' ? r.outGross.toFixed(3) : '—'}</span> },
              { key: 'loss', header: 'Loss (g)', align: 'right', sort: (r) => lossOf(r) ?? -1, render: (r) => { const l = lossOf(r); return <span className="mono">{l === null ? (r.stage === 'Alloying' && r.status === 'Done' ? `+${r3(r.outGross - r.inGross).toFixed(3)} alloy` : '—') : l.toFixed(3)}</span>; } },
              { key: 'lp', header: 'Loss %', align: 'right', hideSm: true, render: (r) => { const l = lossOf(r); return l === null ? '—' : `${((l / r.inGross) * 100).toFixed(2)}%`; } },
              { key: 'st', header: 'Status', render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
            ]}
          />
        </Card>
      )}

      {tab === 'output' && (
        <Card pad={false}>
          <DataTable
            caption="Finished output against target"
            rows={output.filter((o) => jobId === 'All jobs' || o.j.id === jobId)}
            rowKey={(r) => r.j.id}
            columns={[
              { key: 'job', header: 'Job', render: (r) => <Link to="jobs" id={r.j.id} className="link">{r.j.id} · {r.j.title}</Link> },
              { key: 'stage', header: 'Latest stage', render: (r) => (r.lastStage ? `${r.lastStage.stage} · ${r.lastStage.status}` : '—') },
              { key: 'pcs', header: 'Pieces', align: 'right', render: (r) => `${r.pieces} / ${r.j.pieces}` },
              { key: 'target', header: 'Target gross', align: 'right', render: (r) => <span className="mono">{g3(r.target)}</span> },
              { key: 'fg', header: 'Finished gross', align: 'right', render: (r) => <span className="mono">{r.fgGross ? g3(r.fgGross) : '—'}</span> },
              { key: 'var', header: 'vs target', align: 'right', render: (r) => (r.fgGross ? <span className="mono">{((r.fgGross / r.target - 1) * 100).toFixed(1)}%</span> : '—') },
            ]}
          />
        </Card>
      )}
      <StageDialog key={jobId} open={open} onClose={() => setOpen(false)} initialJob={jobId === 'All jobs' ? s.jobs[0].id : jobId} />
    </div>
  );
}

function StageDialog({ open, onClose, initialJob }: { open: boolean; onClose: () => void; initialJob: string }) {
  const s = useAppState();
  const workers = s.parties.filter((p) => p.id !== VAULT && p.role !== 'Manufacturer');
  const [f, setF] = useState({ jobId: initialJob, stage: 'Casting' as Stage, partyId: workers[0]?.id ?? '', inGross: '', outGross: '', pieces: '0', status: 'Done' as 'Done' | 'In progress', note: '' });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const inG = Number(f.inGross) || 0;
  const outG = Number(f.outGross) || 0;
  const submit = () => {
    const res = addProduction({ ...f, date: AS_OF, inGross: inG, outGross: f.status === "Done" ? outG : 0, pieces: Number(f.pieces) || 0 });
    setMsg(res.ok ? { ok: true, text: `Logged ${res.id} in this browser session only — not saved to any server.` } : { ok: false, text: res.error });
  };
  const close = () => {
    setMsg(null);
    onClose();
  };
  return (
    <Dialog
      open={open}
      title="Log production stage"
      onClose={close}
      footer={
        <>
          <Btn onClick={close}>Close</Btn>
          <Btn variant="gold" icon="manufacture" onClick={submit}>Log stage (local demo)</Btn>
        </>
      }
    >
      <DemoNote>No API is connected. Entries are kept in this browser session only.</DemoNote>
      <FormGrid>
        <Field label="Job">
          <select value={f.jobId} onChange={(e) => setF({ ...f, jobId: e.target.value })}>
            {s.jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.id} · {j.title}</option>
            ))}
          </select>
        </Field>
        <Field label="Stage">
          <select value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value as Stage })}>
            {STAGES.map((st) => (
              <option key={st}>{st}</option>
            ))}
          </select>
        </Field>
        <Field label="Performed by">
          <select value={f.partyId} onChange={(e) => setF({ ...f, partyId: e.target.value })}>
            {workers.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as 'Done' | 'In progress' })}>
            <option>Done</option>
            <option>In progress</option>
          </select>
        </Field>
        <Field label="Input weight (g)">
          <input type="number" min={0} step={0.001} value={f.inGross} onChange={(e) => setF({ ...f, inGross: e.target.value })} />
        </Field>
        <Field label="Output weight (g)" hint={f.status === 'Done' ? undefined : 'Not needed while in progress'}>
          <input type="number" min={0} step={0.001} value={f.outGross} disabled={f.status !== 'Done'} onChange={(e) => setF({ ...f, outGross: e.target.value })} />
        </Field>
        <Field label="Pieces">
          <input type="number" min={0} step={1} value={f.pieces} onChange={(e) => setF({ ...f, pieces: e.target.value })} />
        </Field>
        <Field label="Date">
          <input type="date" value={AS_OF} readOnly />
        </Field>
      </FormGrid>
      {f.status === 'Done' && inG > 0 && (
        <p className="calc-preview">
          {f.stage === 'Alloying' ? 'Alloy added' : 'Process loss'}: <b>{g3(Math.abs(r3(inG - outG)))}</b> ({inG ? ((Math.abs(inG - outG) / inG) * 100).toFixed(2) : '0.00'}%)
        </p>
      )}
      <FormMessage result={msg} />
    </Dialog>
  );
}
