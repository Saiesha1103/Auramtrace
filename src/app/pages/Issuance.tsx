import { useState } from 'react';
import { acknowledgeLot, issueLot, useAppState } from '../data/store';
import { AS_OF } from '../data/seed';
import { daysBetween, fine, fmtDate, g3, pct, r3 } from '../data/calc';
import type { Lot } from '../data/types';
import { useLookups } from '../lookups';
import { Link, useRoute } from '../router';
import { Btn, Card, DataTable, DemoNote, Dialog, Field, FormGrid, FormMessage, Kpi, PageHeader, Pill, SearchInput, SelectFilter, Toolbar } from '../ui';

const PURITY_PRESETS = [
  { label: 'Fine bar 999', value: 0.999 },
  { label: 'Fine bar 995', value: 0.995 },
  { label: '22K alloy 916', value: 0.916 },
  { label: '18K alloy 750', value: 0.75 },
];

export function Issuance() {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const { query } = useRoute();
  const [q, setQ] = useState('');
  const [ack, setAck] = useState('All');
  const [open, setOpen] = useState(Boolean(query.get('job')));
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);

  const rows = s.lots.filter(
    (l) => (ack === 'All' || (ack === 'Acknowledged') === l.acknowledged) && `${l.id} ${l.jobId} ${partyName(l.issuedTo)} ${l.source}`.toLowerCase().includes(q.toLowerCase()),
  );
  const pending = s.lots.filter((l) => !l.acknowledged);
  const totalGross = r3(s.lots.reduce((a, l) => a + l.gross, 0));
  const totalFine = r3(s.lots.reduce((a, l) => a + fine(l.gross, l.fineness), 0));

  const doAck = (l: Lot) => {
    const res = acknowledgeLot(l.id, AS_OF);
    setFlash(res.ok ? { ok: true, text: `${l.id} marked acknowledged in this browser session only (local demo — no server record).` } : { ok: false, text: res.error });
  };

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Custody · step 1"
        title="Gold Issuance"
        lede="Lots issued from the vault against jobs, with weight, purity and receipt acknowledgement."
        actions={<Btn variant="gold" icon="plus" onClick={() => setOpen(true)}>Issue lot</Btn>}
      />
      <div className="kpis">
        <Kpi icon="issue" label="Lots issued" value={s.lots.length} />
        <Kpi icon="scale" label="Gross issued" value={g3(totalGross)} />
        <Kpi icon="layers" label="Fine issued" value={g3(totalFine)} />
        <Kpi icon="clock" label="Awaiting acknowledgement" value={pending.length} sub={pending.length ? `oldest ${daysBetween(pending.map((p) => p.date).sort()[0], AS_OF)}d` : 'all signed'} tone={pending.length ? 'warn' : undefined} />
      </div>
      <FormMessage result={flash} />
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SearchInput value={q} onChange={setQ} placeholder="Search lot, job, holder, bar…" />
            <SelectFilter label="Acknowledgement" value={ack} onChange={setAck} options={['All', 'Acknowledged', 'Pending']} />
          </Toolbar>
        </div>
        <DataTable<Lot>
          caption="Issued lots"
          rows={rows}
          rowKey={(r) => r.id}
          initialSort={{ key: 'date', dir: 'desc' }}
          columns={[
            { key: 'id', header: 'Lot', sort: (r) => r.id, render: (r) => <span className="cell-main"><b className="mono">{r.id}</b><small>{r.source}</small></span> },
            { key: 'date', header: 'Issued', sort: (r) => r.date, render: (r) => fmtDate(r.date) },
            { key: 'job', header: 'Job', hideSm: true, render: (r) => <Link to="jobs" id={r.jobId} className="link">{jobLabel(r.jobId)}</Link> },
            { key: 'to', header: 'Issued to', render: (r) => <Link to="karigars" id={r.issuedTo} className="link">{partyName(r.issuedTo)}</Link> },
            { key: 'gross', header: 'Gross', align: 'right', sort: (r) => r.gross, render: (r) => <span className="mono">{g3(r.gross)}</span> },
            { key: 'pur', header: 'Purity', align: 'right', sort: (r) => r.fineness, render: (r) => <span className="mono">{pct(r.fineness)}</span> },
            { key: 'fine', header: 'Fine', align: 'right', sort: (r) => fine(r.gross, r.fineness), render: (r) => <span className="mono gold">{g3(fine(r.gross, r.fineness))}</span> },
            {
              key: 'ack',
              header: 'Acknowledgement',
              render: (r) =>
                r.acknowledged ? (
                  <Pill tone="ok">Signed {r.ackAt ? fmtDate(r.ackAt) : ''}</Pill>
                ) : (
                  <span className="row-actions" style={{ justifyContent: 'flex-start' }}>
                    <Pill tone="warn">Pending {daysBetween(r.date, AS_OF)}d</Pill>
                    <Btn size="sm" variant="quiet" icon="check" onClick={() => doAck(r)}>Record</Btn>
                  </span>
                ),
            },
          ]}
        />
      </Card>
      <IssueDialog open={open} onClose={() => setOpen(false)} initialJob={query.get('job') ?? ''} />
    </div>
  );
}

function IssueDialog({ open, onClose, initialJob }: { open: boolean; onClose: () => void; initialJob: string }) {
  const s = useAppState();
  const holders = s.parties.filter((p) => p.role === 'Head karigar' || p.role === 'Karigar');
  const firstJob = initialJob || s.jobs[0]?.id || '';
  const defaultTo = (jid: string) => s.jobs.find((j) => j.id === jid)?.headKarigarId ?? holders[0]?.id ?? '';
  const [f, setF] = useState({ jobId: firstJob, issuedTo: defaultTo(firstJob), gross: '', fineness: '0.995', source: '', date: AS_OF });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const g = Number(f.gross) || 0;
  const fn = Number(f.fineness) || 0;

  const submit = () => {
    const res = issueLot({ jobId: f.jobId, issuedTo: f.issuedTo, gross: g, fineness: fn, date: f.date, source: f.source || 'Unspecified bar' });
    setMsg(res.ok ? { ok: true, text: `Issued ${res.id} in this browser session only — not saved to any server. Acknowledgement is pending.` } : { ok: false, text: res.error });
    if (res.ok) setF({ ...f, gross: '', source: '' });
  };
  const close = () => {
    setMsg(null);
    onClose();
  };

  return (
    <Dialog
      open={open}
      title="Issue gold lot"
      onClose={close}
      footer={
        <>
          <Btn onClick={close}>Close</Btn>
          <Btn variant="gold" icon="issue" onClick={submit}>Issue lot (local demo)</Btn>
        </>
      }
    >
      <DemoNote>No API is connected. The lot exists only in this browser session.</DemoNote>
      <FormGrid>
        <Field label="Job">
          <select value={f.jobId} onChange={(e) => setF({ ...f, jobId: e.target.value, issuedTo: defaultTo(e.target.value) })}>
            {s.jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.id} · {j.title}</option>
            ))}
          </select>
        </Field>
        <Field label="Issue to">
          <select value={f.issuedTo} onChange={(e) => setF({ ...f, issuedTo: e.target.value })}>
            {holders.map((h) => (
              <option key={h.id} value={h.id}>{h.name} ({h.role})</option>
            ))}
          </select>
        </Field>
        <Field label="Gross weight (g)">
          <input type="number" min={0} step={0.001} value={f.gross} onChange={(e) => setF({ ...f, gross: e.target.value })} />
        </Field>
        <Field label="Purity (fineness)" hint="Parts per 1, e.g. 0.995">
          <input type="number" min={0} max={0.9999} step={0.001} value={f.fineness} onChange={(e) => setF({ ...f, fineness: e.target.value })} list="purity-presets" />
          <datalist id="purity-presets">
            {PURITY_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </datalist>
        </Field>
        <Field label="Source bar / lot">
          <input value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} placeholder="Bar 995 · B-…" />
        </Field>
        <Field label="Issue date">
          <input type="date" value={f.date} max={AS_OF} onChange={(e) => setF({ ...f, date: e.target.value })} />
        </Field>
      </FormGrid>
      <p className="calc-preview">
        Fine gold: <b>{g3(fine(g, fn))}</b> = {g.toFixed(3)} g × {pct(fn)}
      </p>
      <FormMessage result={msg} />
    </Dialog>
  );
}
