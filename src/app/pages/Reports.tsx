import { useEffect, useMemo, useState } from 'react';
import { useAppState } from '../data/store';
import { fmtDate, g3, jobStatus, ledger, pct, reconcile, type LedgerEvent } from '../data/calc';
import type { AuditEntry } from '../data/types';
import { useLookups } from '../lookups';
import { Link, useRoute } from '../router';
import { Btn, Card, DataTable, DemoNote, Field, PageHeader, Pill, SearchInput, SelectFilter, Tabs, Toolbar, downloadCsv, statusTone } from '../ui';

type Tab = 'movement' | 'jobs' | 'audit';

export function Reports() {
  const { query } = useRoute();
  const initial = (query.get('tab') as Tab) || 'movement';
  const [tab, setTab] = useState<Tab>(['movement', 'jobs', 'audit'].includes(initial) ? initial : 'movement');
  // follow ?tab= links even when already on this page
  useEffect(() => {
    if (['movement', 'jobs', 'audit'].includes(initial)) setTab(initial);
  }, [initial]);
  return (
    <div className="stack">
      <PageHeader eyebrow="Control" title="Reports & Audit" lede="Gold movement, job summaries and the full audit trail. Exports download exactly what is on screen." />
      <Tabs label="Report type" value={tab} onChange={setTab} tabs={[{ key: 'movement', label: 'Movement report' }, { key: 'jobs', label: 'Job report' }, { key: 'audit', label: 'Audit history' }]} />
      {tab === 'movement' && <Movement />}
      {tab === 'jobs' && <JobReport />}
      {tab === 'audit' && <Audit />}
    </div>
  );
}

function Movement() {
  const s = useAppState();
  const { partyName } = useLookups();
  const all = useMemo(() => ledger(s), [s]);
  const [kind, setKind] = useState('All');
  const [party, setParty] = useState('All');
  const [from, setFrom] = useState('2026-10-01');
  const [to, setTo] = useState('2026-11-30');
  const rows = all.filter((e) => (kind === 'All' || e.kind === kind) && (party === 'All' || e.from === party || e.to === party) && e.date >= from && e.date <= to);
  const exp = () =>
    downloadCsv(
      `aurumtrace-movement-${from}-to-${to}.csv`,
      ['Date', 'Ref', 'Kind', 'Job', 'From', 'To', 'Gross g', 'Fineness', 'Fine g', 'Detail', 'Data source'],
      rows.map((e) => [e.date, e.id, e.kind, e.jobId, partyName(e.from), partyName(e.to), e.gross.toFixed(3), e.fineness, e.fine.toFixed(3), e.detail, 'synthetic demo']),
    );
  return (
    <Card pad={false}>
      <div style={{ padding: '16px 20px 0' }}>
        <Toolbar>
          <SelectFilter label="Kind" value={kind} onChange={setKind} options={['All', 'Issue', 'Transfer', 'Return']} />
          <SelectFilter label="Party" value={party} onChange={setParty} options={['All', ...s.parties.map((p) => ({ value: p.id, label: p.name }))]} />
          <Field label="From">
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To">
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <Btn icon="download" onClick={exp} disabled={!rows.length}>Export CSV ({rows.length})</Btn>
        </Toolbar>
      </div>
      <DataTable<LedgerEvent>
        caption="Gold movement report"
        rows={rows}
        rowKey={(r) => r.id}
        initialSort={{ key: 'date', dir: 'desc' }}
        columns={[
          { key: 'date', header: 'Date', sort: (r) => r.date + r.id, render: (r) => fmtDate(r.date) },
          { key: 'id', header: 'Ref', render: (r) => <span className="mono">{r.id}</span> },
          { key: 'kind', header: 'Kind', sort: (r) => r.kind, render: (r) => r.kind },
          { key: 'job', header: 'Job', render: (r) => <Link to="jobs" id={r.jobId} className="link mono">{r.jobId}</Link> },
          { key: 'route', header: 'From → To', hideSm: true, render: (r) => `${partyName(r.from)} → ${partyName(r.to)}` },
          { key: 'gross', header: 'Gross', align: 'right', render: (r) => <span className="mono">{g3(r.gross)}</span> },
          { key: 'pur', header: 'Purity', align: 'right', hideSm: true, render: (r) => <span className="mono">{pct(r.fineness)}</span> },
          { key: 'fine', header: 'Fine', align: 'right', sort: (r) => r.fine, render: (r) => <span className="mono gold">{g3(r.fine)}</span> },
        ]}
      />
    </Card>
  );
}

function JobReport() {
  const s = useAppState();
  const { partyName } = useLookups();
  const rows = useMemo(() => s.jobs.map((j) => ({ j, st: jobStatus(s, j), rec: reconcile(s, j) })), [s]);
  const exp = () =>
    downloadCsv(
      'aurumtrace-job-report.csv',
      ['Job', 'Title', 'Karat', 'Pieces', 'Head karigar', 'Deadline', 'Status', 'Issued fine g', 'Returned fine g', 'Outstanding g', 'Allowance g', 'Unexplained g', 'Data source'],
      rows.map((r) => [r.j.id, r.j.title, r.j.karat, r.j.pieces, partyName(r.j.headKarigarId), r.j.deadline, r.st, r.rec.issuedFine.toFixed(3), r.rec.returnedFine.toFixed(3), r.rec.outstandingFine.toFixed(3), r.rec.allowanceFine.toFixed(3), r.rec.unexplainedFine.toFixed(3), 'synthetic demo']),
    );
  return (
    <Card pad={false} title="Job report" actions={<Btn icon="download" onClick={exp}>Export CSV</Btn>}>
      <DataTable
        caption="Job report"
        rows={rows}
        rowKey={(r) => r.j.id}
        columns={[
          { key: 'job', header: 'Job', sort: (r) => r.j.id, render: (r) => <Link to="jobs" id={r.j.id} className="link">{r.j.id} · {r.j.title}</Link> },
          { key: 'st', header: 'Status', sort: (r) => r.st, render: (r) => <Pill tone={statusTone(r.st)}>{r.st}</Pill> },
          { key: 'dl', header: 'Deadline', sort: (r) => r.j.deadline, render: (r) => fmtDate(r.j.deadline) },
          { key: 'iss', header: 'Issued', align: 'right', sort: (r) => r.rec.issuedFine, render: (r) => <span className="mono">{g3(r.rec.issuedFine)}</span> },
          { key: 'ret', header: 'Returned', align: 'right', render: (r) => <span className="mono">{g3(r.rec.returnedFine)}</span> },
          { key: 'out', header: 'Outstanding', align: 'right', hideSm: true, render: (r) => <span className="mono">{g3(r.rec.outstandingFine)}</span> },
          { key: 'unexp', header: 'Unexplained', align: 'right', sort: (r) => r.rec.unexplainedFine, render: (r) => <span className={`mono ${r.rec.unexplainedFine ? 'alert-text' : ''}`}>{g3(r.rec.unexplainedFine)}</span> },
        ]}
      />
    </Card>
  );
}

function Audit() {
  const s = useAppState();
  const [src, setSrc] = useState('All');
  const [q, setQ] = useState('');
  const rows = s.audit.filter((a) => (src === 'All' || (src === 'Local demo actions') === (a.source === 'local-demo')) && `${a.action} ${a.actor} ${a.target}`.toLowerCase().includes(q.toLowerCase()));
  const exp = () =>
    downloadCsv(
      'aurumtrace-audit.csv',
      ['When', 'Id', 'Actor', 'Action', 'Target', 'Source'],
      rows.map((a) => [a.at, a.id, a.actor, a.action, a.target, a.source === 'local-demo' ? 'local demo session (not persisted)' : 'synthetic history']),
    );
  return (
    <div className="stack">
      <DemoNote>“Synthetic history” entries are invented seed data. “Local demo” entries are actions taken in this browser session; they were not sent anywhere and vanish on reload.</DemoNote>
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SearchInput value={q} onChange={setQ} placeholder="Search action, actor, job…" />
            <SelectFilter label="Source" value={src} onChange={setSrc} options={['All', 'Synthetic history', 'Local demo actions']} />
            <Btn icon="download" onClick={exp} disabled={!rows.length}>Export CSV</Btn>
          </Toolbar>
        </div>
        <DataTable<AuditEntry>
          caption="Audit history"
          rows={rows}
          rowKey={(r) => r.id}
          initialSort={{ key: 'at', dir: 'desc' }}
          columns={[
            { key: 'at', header: 'When', sort: (r) => r.at, render: (r) => <span className="mono">{r.at.replace('T', ' ')}</span> },
            { key: 'actor', header: 'Actor', sort: (r) => r.actor, render: (r) => r.actor },
            { key: 'action', header: 'Action', render: (r) => <span style={{ whiteSpace: 'normal' }}>{r.action}</span> },
            { key: 'target', header: 'Target', render: (r) => (r.target.startsWith('J-') ? <Link to="jobs" id={r.target} className="link mono">{r.target}</Link> : <span className="mono">{r.target}</span>) },
            { key: 'src', header: 'Source', render: (r) => (r.source === 'local-demo' ? <Pill tone="warn" icon={null}>Local demo</Pill> : <Pill tone="muted" icon={null}>Synthetic</Pill>) },
          ]}
        />
      </Card>
    </div>
  );
}
