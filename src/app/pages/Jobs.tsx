import { useMemo, useState } from 'react';
import { createJob, useAppState } from '../data/store';
import { AS_OF } from '../data/seed';
import { custody, daysBetween, fmtDate, g3, isOverdue, jobStatus, ledger, pct, r3, reconcile, returnFine } from '../data/calc';
import type { Job } from '../data/types';
import { useLookups } from '../lookups';
import { Link, navigate, useRoute } from '../router';
import { Btn, Card, DataTable, DemoNote, Dialog, Empty, Field, FormGrid, FormMessage, KeyValues, Kpi, PageHeader, Pill, SearchInput, SelectFilter, Tabs, Timeline, Toolbar, statusTone } from '../ui';

const KARAT_FINENESS = { '24K': 0.995, '22K': 0.916, '18K': 0.75 } as const;
const STATUSES = ['All statuses', 'Draft', 'Issued', 'In production', 'Returned', 'Reconciled', 'Settled'];

export function Jobs({ id }: { id?: string }) {
  return id ? <JobDetail id={id} /> : <JobList />;
}

function deadlineLabel(job: Job, overdue: boolean) {
  const d = daysBetween(AS_OF, job.deadline);
  if (overdue) return <Pill tone="alert">{-d}d overdue</Pill>;
  return <span className="muted">{d === 0 ? 'Today' : d > 0 ? `in ${d}d` : fmtDate(job.deadline)}</span>;
}

function JobList() {
  const s = useAppState();
  const { partyName } = useLookups();
  const { query } = useRoute();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState(query.get('status') ?? 'All statuses');
  const [open, setOpen] = useState(false);
  const rows = s.jobs
    .map((j) => ({ j, st: jobStatus(s, j), od: isOverdue(s, j), rec: reconcile(s, j) }))
    .filter((r) => (status === 'All statuses' || r.st === status) && `${r.j.id} ${r.j.title} ${r.j.orderRef}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Work orders"
        title="Jobs"
        lede="Every manufacturing job with its specification, deadline and gold position."
        actions={<Btn variant="gold" icon="plus" onClick={() => setOpen(true)}>New job</Btn>}
      />
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SearchInput value={q} onChange={setQ} placeholder="Search job, title, order…" />
            <SelectFilter label="Status" value={status} onChange={setStatus} options={STATUSES} />
          </Toolbar>
        </div>
        <DataTable
          caption="Jobs"
          rows={rows}
          rowKey={(r) => r.j.id}
          onRowClick={(r) => navigate('jobs', r.j.id)}
          initialSort={{ key: 'deadline', dir: 'asc' }}
          columns={[
            { key: 'id', header: 'Job', sort: (r) => r.j.id, render: (r) => <span className="cell-main"><b>{r.j.title}</b><small className="mono">{r.j.id} · {r.j.orderRef}</small></span> },
            { key: 'spec', header: 'Spec', hideSm: true, render: (r) => `${r.j.pieces} pcs · ${r.j.karat}` },
            { key: 'head', header: 'Head karigar', hideSm: true, sort: (r) => partyName(r.j.headKarigarId), render: (r) => partyName(r.j.headKarigarId) },
            { key: 'status', header: 'Status', sort: (r) => r.st, render: (r) => <Pill tone={statusTone(r.st)}>{r.st}</Pill> },
            { key: 'deadline', header: 'Deadline', sort: (r) => r.j.deadline, render: (r) => <span className="cell-main"><span>{fmtDate(r.j.deadline)}</span><small>{deadlineLabel(r.j, r.od)}</small></span> },
            { key: 'issued', header: 'Issued (fine)', align: 'right', sort: (r) => r.rec.issuedFine, render: (r) => <span className="mono">{r.rec.issuedFine ? g3(r.rec.issuedFine) : '—'}</span> },
            { key: 'out', header: 'Outstanding', align: 'right', hideSm: true, sort: (r) => r.rec.outstandingFine, render: (r) => <span className="mono">{r.rec.issuedFine ? g3(r.rec.outstandingFine) : '—'}</span> },
          ]}
        />
      </Card>
      <NewJobDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function NewJobDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const s = useAppState();
  const heads = s.parties.filter((p) => p.role === 'Head karigar');
  const blank = { title: '', orderRef: '', karat: '22K' as Job['karat'], pieces: '1', targetGrossPerPiece: '', headKarigarId: heads[0]?.id ?? '', lossAllowancePct: '1.0', deadline: '', notes: '' };
  const [f, setF] = useState(blank);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const up = (k: keyof typeof blank) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const fineTarget = r3((Number(f.pieces) || 0) * (Number(f.targetGrossPerPiece) || 0) * KARAT_FINENESS[f.karat]);

  const submit = () => {
    const res = createJob({
      title: f.title,
      orderRef: f.orderRef || '—',
      karat: f.karat,
      fineness: KARAT_FINENESS[f.karat],
      pieces: Number(f.pieces),
      targetGrossPerPiece: Number(f.targetGrossPerPiece),
      headKarigarId: f.headKarigarId,
      lossAllowancePct: Number(f.lossAllowancePct),
      createdAt: AS_OF,
      deadline: f.deadline || AS_OF,
      notes: f.notes,
    });
    if (res.ok) {
      setMsg({ ok: true, text: `Created ${res.id} in this browser session only — not saved to any server.` });
      setF(blank);
    } else setMsg({ ok: false, text: res.error });
  };
  const close = () => {
    setMsg(null);
    onClose();
  };

  return (
    <Dialog
      open={open}
      title="New job"
      onClose={close}
      footer={
        <>
          <Btn onClick={close}>Close</Btn>
          <Btn variant="gold" icon="plus" onClick={submit}>Create job (local demo)</Btn>
        </>
      }
    >
      <DemoNote>No API is connected. The job is added to this browser session only and disappears on reload.</DemoNote>
      <FormGrid>
        <Field label="Title" wide>
          <input value={f.title} onChange={up('title')} placeholder="e.g. Temple bangles" />
        </Field>
        <Field label="Order reference">
          <input value={f.orderRef} onChange={up('orderRef')} placeholder="SO-…" />
        </Field>
        <Field label="Head karigar">
          <select value={f.headKarigarId} onChange={up('headKarigarId')}>
            {heads.map((h) => (
              <option key={h.id} value={h.id}>{h.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Karat" hint={`Fineness ${pct(KARAT_FINENESS[f.karat])}`}>
          <select value={f.karat} onChange={up('karat')}>
            {Object.keys(KARAT_FINENESS).map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </Field>
        <Field label="Pieces">
          <input type="number" min={1} step={1} value={f.pieces} onChange={up('pieces')} />
        </Field>
        <Field label="Target gross per piece (g)">
          <input type="number" min={0} step={0.001} value={f.targetGrossPerPiece} onChange={up('targetGrossPerPiece')} />
        </Field>
        <Field label="Loss allowance (%)" hint="0–5%">
          <input type="number" min={0} max={5} step={0.1} value={f.lossAllowancePct} onChange={up('lossAllowancePct')} />
        </Field>
        <Field label="Deadline">
          <input type="date" min={AS_OF} value={f.deadline} onChange={up('deadline')} />
        </Field>
        <Field label="Specification notes" wide>
          <textarea value={f.notes} onChange={up('notes')} placeholder="Design, sizes, finish, stones…" />
        </Field>
      </FormGrid>
      <p className="calc-preview">
        Target fine gold: <b>{g3(fineTarget)}</b> = {f.pieces || 0} pcs × {f.targetGrossPerPiece || 0} g × {pct(KARAT_FINENESS[f.karat])}
      </p>
      <FormMessage result={msg} />
    </Dialog>
  );
}

function JobDetail({ id }: { id: string }) {
  const s = useAppState();
  const { partyName } = useLookups();
  const [tab, setTab] = useState<'overview' | 'custody' | 'production' | 'returns'>('overview');
  const job = s.jobs.find((j) => j.id === id);
  const data = useMemo(() => {
    if (!job) return null;
    return {
      st: jobStatus(s, job),
      od: isOverdue(s, job),
      rec: reconcile(s, job),
      ev: ledger(s).filter((e) => e.jobId === id),
      holders: [...custody(s, id).entries()].filter(([, v]) => Math.abs(v) > 0.0005),
      prod: s.production.filter((p) => p.jobId === id),
      rets: s.returns.filter((r) => r.jobId === id),
    };
  }, [s, job, id]);

  if (!job || !data)
    return (
      <Card>
        <Empty title={`No job “${id}”`}>
          <Link to="jobs" className="link">Back to jobs</Link>
        </Empty>
      </Card>
    );
  const targetGross = r3(job.pieces * job.targetGrossPerPiece);
  const fgPieces = data.rets.filter((r) => r.type === 'Finished goods').reduce((a, r) => a + r.pieces, 0);

  return (
    <div className="stack">
      <PageHeader
        eyebrow={`${job.id} · ${job.orderRef}`}
        title={job.title}
        lede={job.notes}
        actions={
          <>
            <Pill tone={statusTone(data.st)}>{data.st}</Pill>
            {data.od && <Pill tone="alert">Overdue</Pill>}
            <Btn icon="issue" onClick={() => navigate('issuance', undefined, { job: id })}>Issue gold</Btn>
            <Btn icon="scale" onClick={() => navigate('reconciliation', id)}>Reconciliation</Btn>
          </>
        }
      />
      <div className="kpis">
        <Kpi icon="issue" label="Issued (fine)" value={g3(data.rec.issuedFine)} />
        <Kpi icon="return" label="Returned (fine)" value={g3(data.rec.returnedFine)} />
        <Kpi icon="layers" label="Outstanding" value={g3(data.rec.outstandingFine)} sub={data.rec.closed ? 'job closed' : 'still in custody'} />
        <Kpi icon="manufacture" label="Pieces returned" value={`${fgPieces} / ${job.pieces}`} />
      </div>
      <Tabs
        label="Job sections"
        value={tab}
        onChange={setTab}
        tabs={[
          { key: 'overview', label: 'Specification' },
          { key: 'custody', label: 'Custody', count: data.ev.length },
          { key: 'production', label: 'Production', count: data.prod.length },
          { key: 'returns', label: 'Returns', count: data.rets.length },
        ]}
      />
      {tab === 'overview' && (
        <div className="grid-2">
          <Card title="Specification & deadline">
            <KeyValues
              items={[
                ['Karat / fineness', `${job.karat} · ${pct(job.fineness)}`],
                ['Pieces', job.pieces],
                ['Target gross / piece', g3(job.targetGrossPerPiece)],
                ['Target gross total', g3(targetGross)],
                ['Target fine total', g3(r3(targetGross * job.fineness))],
                ['Loss allowance', `${job.lossAllowancePct}%`],
                ['Created', fmtDate(job.createdAt)],
                ['Deadline', <>{fmtDate(job.deadline)} {deadlineLabel(job, data.od)}</>],
                ['Head karigar', <Link to="karigars" id={job.headKarigarId} className="link">{partyName(job.headKarigarId)}</Link>],
              ]}
            />
          </Card>
          <Card title="Current holders (fine)">
            {data.holders.length ? (
              <ul className="list-plain">
                {data.holders.map(([pid, v]) => (
                  <li key={pid} className="doc-item">
                    <span className="mono gold">{g3(v)}</span>
                    <span>
                      <Link to="karigars" id={pid} className="link">{partyName(pid)}</Link>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title={data.rec.issuedFine ? 'All gold returned' : 'No gold issued yet'} />
            )}
          </Card>
        </div>
      )}
      {tab === 'custody' && (
        <Card title="Custody timeline">
          <Timeline
            items={data.ev.map((e) => ({
              id: e.id,
              date: fmtDate(e.date),
              icon: e.kind === 'Issue' ? 'issue' : e.kind === 'Transfer' ? 'transfer' : 'return',
              title: `${e.kind}: ${partyName(e.from)} → ${partyName(e.to)}`,
              meta: `${e.id} · ${e.detail} · ${e.gross.toFixed(3)} g @ ${pct(e.fineness)}`,
              value: g3(e.fine),
            }))}
          />
        </Card>
      )}
      {tab === 'production' && (
        <Card pad={false} title="Production stages" actions={<Link to="production" query={{ job: id }} className="link">Open in Production</Link>}>
          <DataTable
            caption="Production stages"
            rows={data.prod}
            rowKey={(r) => r.id}
            empty="No production logged yet."
            columns={[
              { key: 'd', header: 'Date', render: (r) => fmtDate(r.date) },
              { key: 'stage', header: 'Stage', render: (r) => r.stage },
              { key: 'who', header: 'By', render: (r) => partyName(r.partyId) },
              { key: 'in', header: 'In (g)', align: 'right', render: (r) => <span className="mono">{r.inGross.toFixed(3)}</span> },
              { key: 'out', header: 'Out (g)', align: 'right', render: (r) => <span className="mono">{r.status === 'Done' ? r.outGross.toFixed(3) : '—'}</span> },
              { key: 'st', header: 'Status', render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
            ]}
          />
        </Card>
      )}
      {tab === 'returns' && (
        <Card pad={false} title="Returns" actions={<Link to="returns" query={{ job: id }} className="link">Open in Returns</Link>}>
          <DataTable
            caption="Returns"
            rows={data.rets}
            rowKey={(r) => r.id}
            empty="Nothing returned yet."
            columns={[
              { key: 'd', header: 'Date', render: (r) => fmtDate(r.date) },
              { key: 'id', header: 'Return', render: (r) => <span className="mono">{r.id}</span> },
              { key: 't', header: 'Type', render: (r) => <>{r.type} {r.partial && <Pill tone="warn" icon={null}>Partial</Pill>}</> },
              { key: 'g', header: 'Gross', align: 'right', render: (r) => <span className="mono">{g3(r.gross)}</span> },
              { key: 'f', header: 'Fine', align: 'right', render: (r) => <span className="mono">{g3(returnFine(r))}</span> },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
