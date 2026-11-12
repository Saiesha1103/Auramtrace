import { useMemo, useState } from 'react';
import { createTransfer, useAppState } from '../data/store';
import { AS_OF, VAULT } from '../data/seed';
import { custody, fine, fmtDate, g3, ledger, pct, r3 } from '../data/calc';
import type { Transfer, TransferKind } from '../data/types';
import { useLookups } from '../lookups';
import { Link, useRoute } from '../router';
import { BarList, Btn, Card, DataTable, DemoNote, Dialog, Field, FormGrid, FormMessage, PageHeader, Pill, SelectFilter, Tabs, Timeline, Toolbar } from '../ui';

export function Transfers() {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const { query } = useRoute();
  const [tab, setTab] = useState<'register' | 'timeline'>(query.get('job') ? 'timeline' : 'register');
  const [kind, setKind] = useState('All kinds');
  const [jobId, setJobId] = useState(query.get('job') ?? 'J-1168');
  const [open, setOpen] = useState(false);

  const rows = s.transfers.filter((t) => kind === 'All kinds' || t.kind === kind);
  const jobEvents = useMemo(() => ledger(s).filter((e) => e.jobId === jobId), [s, jobId]);
  const holders = useMemo(() => [...custody(s, jobId).entries()].filter(([, v]) => v > 0.0005), [s, jobId]);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Custody · step 2"
        title="Transfers"
        lede="Movement of gold between custody levels — full hand-offs, partial transfers and job splits."
        actions={<Btn variant="gold" icon="transfer" onClick={() => setOpen(true)}>New transfer</Btn>}
      />
      <Tabs label="Transfer views" value={tab} onChange={setTab} tabs={[{ key: 'register', label: 'Register', count: s.transfers.length }, { key: 'timeline', label: 'Custody timeline' }]} />

      {tab === 'register' ? (
        <Card pad={false}>
          <div style={{ padding: '16px 20px 0' }}>
            <Toolbar>
              <SelectFilter label="Kind" value={kind} onChange={setKind} options={['All kinds', 'Full', 'Partial', 'Split']} />
            </Toolbar>
          </div>
          <DataTable<Transfer>
            caption="Transfer register"
            rows={rows}
            rowKey={(r) => r.id}
            initialSort={{ key: 'date', dir: 'desc' }}
            columns={[
              { key: 'id', header: 'Transfer', sort: (r) => r.id, render: (r) => <span className="cell-main"><b className="mono">{r.id}</b><small>{r.purpose}</small></span> },
              { key: 'date', header: 'Date', sort: (r) => r.date, render: (r) => fmtDate(r.date) },
              { key: 'job', header: 'Job', hideSm: true, render: (r) => <Link to="jobs" id={r.jobId} className="link">{jobLabel(r.jobId)}</Link> },
              { key: 'route', header: 'From → To', render: (r) => `${partyName(r.from)} → ${partyName(r.to)}` },
              { key: 'kind', header: 'Kind', sort: (r) => r.kind, render: (r) => <Pill tone={r.kind === 'Full' ? 'muted' : 'gold'} icon={null}>{r.kind}</Pill> },
              { key: 'gross', header: 'Gross', align: 'right', sort: (r) => r.gross, render: (r) => <span className="mono">{g3(r.gross)}</span> },
              { key: 'fine', header: 'Fine', align: 'right', sort: (r) => fine(r.gross, r.fineness), render: (r) => <span className="mono gold">{g3(fine(r.gross, r.fineness))}</span> },
            ]}
          />
        </Card>
      ) : (
        <>
          <Toolbar>
            <SelectFilter label="Job" value={jobId} onChange={setJobId} options={s.jobs.map((j) => ({ value: j.id, label: `${j.id} · ${j.title}` }))} />
          </Toolbar>
          <div className="grid-2">
            <Card title={`Custody timeline · ${jobId}`}>
              <Timeline
                items={jobEvents.map((e) => ({
                  id: e.id,
                  date: fmtDate(e.date),
                  icon: e.kind === 'Issue' ? 'issue' : e.kind === 'Transfer' ? 'transfer' : 'return',
                  title: `${partyName(e.from)} → ${partyName(e.to)}`,
                  meta: `${e.id} · ${e.kind} · ${e.detail}`,
                  value: g3(e.fine),
                }))}
              />
            </Card>
            <Card title="Who holds it now (fine)">
              {holders.length ? <BarList items={holders.map(([id, v]) => ({ key: id, label: partyName(id), value: v }))} format={g3} /> : <p className="muted">Nothing outstanding on this job.</p>}
            </Card>
          </div>
        </>
      )}
      <TransferDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

interface Leg {
  to: string;
  gross: string;
}

function TransferDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const s = useAppState();
  const { partyName } = useLookups();
  const people = s.parties.filter((p) => p.id !== VAULT);
  const [jobId, setJobId] = useState(s.jobs.find((j) => j.id === 'J-1191')?.id ?? s.jobs[0].id);
  const holdersOnJob = useMemo(() => [...custody(s, jobId).entries()].filter(([, v]) => v > 0.0005), [s, jobId]);
  const [from, setFrom] = useState('');
  const sender = from || holdersOnJob[0]?.[0] || '';
  const held = custody(s, jobId).get(sender) ?? 0;
  const [mode, setMode] = useState<'single' | 'split'>('single');
  const [fineness, setFineness] = useState('0.995');
  const [purpose, setPurpose] = useState('');
  const [legs, setLegs] = useState<Leg[]>([{ to: '', gross: '' }]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const fn = Number(fineness) || 0;
  const movingFine = r3(legs.reduce((a, l) => a + fine(Number(l.gross) || 0, fn), 0));

  const submit = () => {
    if (!sender) return setMsg({ ok: false, text: 'Nobody holds gold on this job yet — issue a lot first.' });
    if (movingFine > held + 0.0005) return setMsg({ ok: false, text: `${partyName(sender)} holds ${g3(held)} fine on ${jobId}; these legs move ${g3(movingFine)}.` });
    const done: string[] = [];
    for (const leg of legs) {
      const kind: TransferKind = mode === 'split' ? 'Split' : fine(Number(leg.gross) || 0, fn) >= held - 0.0005 ? 'Full' : 'Partial';
      const res = createTransfer({ jobId, from: sender, to: leg.to, gross: Number(leg.gross), fineness: fn, date: AS_OF, kind, purpose: purpose || (mode === 'split' ? 'Job split' : 'Hand-off') });
      if (!res.ok) return setMsg({ ok: false, text: `${done.length ? `Recorded ${done.join(', ')}; then stopped: ` : ''}${res.error}` });
      done.push(res.id);
    }
    setMsg({ ok: true, text: `Recorded ${done.join(', ')} in this browser session only — not saved to any server.` });
    setLegs([{ to: '', gross: '' }]);
  };
  const close = () => {
    setMsg(null);
    onClose();
  };

  return (
    <Dialog
      open={open}
      title="New transfer"
      onClose={close}
      footer={
        <>
          <Btn onClick={close}>Close</Btn>
          <Btn variant="gold" icon="transfer" onClick={submit}>Record transfer (local demo)</Btn>
        </>
      }
    >
      <DemoNote>No API is connected. Transfers are validated against the custody ledger and kept in this browser session only.</DemoNote>
      <Tabs label="Transfer mode" value={mode} onChange={(m) => { setMode(m); setLegs(m === 'split' ? [{ to: '', gross: '' }, { to: '', gross: '' }] : [{ to: '', gross: '' }]); }} tabs={[{ key: 'single', label: 'Single / partial' }, { key: 'split', label: 'Split job' }]} />
      <FormGrid>
        <Field label="Job">
          <select value={jobId} onChange={(e) => { setJobId(e.target.value); setFrom(''); }}>
            {s.jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.id} · {j.title}</option>
            ))}
          </select>
        </Field>
        <Field label="From (current holder)" hint={sender ? `Holds ${g3(held)} fine on this job` : 'No holders on this job'}>
          <select value={sender} onChange={(e) => setFrom(e.target.value)}>
            {holdersOnJob.map(([id]) => (
              <option key={id} value={id}>{partyName(id)}</option>
            ))}
          </select>
        </Field>
        <Field label="Purity of metal moved" hint="0.995 bar, 0.916 after 22K alloying">
          <input type="number" min={0} max={0.9999} step={0.001} value={fineness} onChange={(e) => setFineness(e.target.value)} />
        </Field>
        <Field label="Purpose">
          <input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="e.g. Batch A — casting" />
        </Field>
        {legs.map((leg, i) => (
          <div key={i} className="field-wide form-grid">
            <Field label={mode === 'split' ? `Recipient ${i + 1}` : 'To'}>
              <select value={leg.to} onChange={(e) => setLegs(legs.map((l, j) => (j === i ? { ...l, to: e.target.value } : l)))}>
                <option value="">Choose…</option>
                {people.filter((p) => p.id !== sender).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.role})</option>
                ))}
              </select>
            </Field>
            <Field label="Gross weight (g)">
              <input type="number" min={0} step={0.001} value={leg.gross} onChange={(e) => setLegs(legs.map((l, j) => (j === i ? { ...l, gross: e.target.value } : l)))} />
            </Field>
          </div>
        ))}
      </FormGrid>
      {mode === 'split' && legs.length < 4 && (
        <Btn size="sm" variant="quiet" icon="plus" onClick={() => setLegs([...legs, { to: '', gross: '' }])}>Add recipient</Btn>
      )}
      <p className="calc-preview">
        Moving <b>{g3(movingFine)}</b> fine of <b>{g3(held)}</b> held · remaining with sender <b>{g3(r3(held - movingFine))}</b> · purity {pct(fn)}
      </p>
      <FormMessage result={msg} />
    </Dialog>
  );
}
