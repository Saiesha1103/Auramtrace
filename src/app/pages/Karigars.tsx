import { useMemo, useState } from 'react';
import { useAppState } from '../data/store';
import { VAULT } from '../data/seed';
import { custody, fmtDate, g3, inr, jobStatus, ledger, r3 } from '../data/calc';
import type { Party } from '../data/types';
import { useLookups } from '../lookups';
import { Link, navigate, useRoute } from '../router';
import { Card, DataTable, Empty, KeyValues, Kpi, PageHeader, Pill, SearchInput, SelectFilter, Tabs, Timeline, Toolbar, statusTone } from '../ui';

const initials = (n: string) =>
  n
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('');

export function Karigars({ id }: { id?: string }) {
  return id ? <Profile id={id} /> : <Directory />;
}

function Directory() {
  const s = useAppState();
  const { query } = useRoute();
  const [tab, setTab] = useState<'directory' | 'hierarchy'>(query.get('tab') === 'hierarchy' ? 'hierarchy' : 'directory');
  const [q, setQ] = useState('');
  const [role, setRole] = useState('All roles');
  const hold = useMemo(() => custody(s), [s]);
  const people = s.parties.filter((p) => p.id !== VAULT);
  const rows = people.filter((p) => (role === 'All roles' || p.role === role) && `${p.id} ${p.name} ${p.unit} ${p.skills.join(' ')}`.toLowerCase().includes(q.toLowerCase()));
  const activeJobs = (pid: string) => new Set(ledger(s).filter((e) => e.to === pid || e.from === pid).map((e) => e.jobId)).size;

  return (
    <div className="stack">
      <PageHeader eyebrow="People" title="Karigars" lede="Head karigars, karigars and subcontractors, with the fine gold each currently holds." />
      <Tabs label="Karigar views" value={tab} onChange={setTab} tabs={[{ key: 'directory', label: 'Directory', count: people.length }, { key: 'hierarchy', label: 'Hierarchy' }]} />

      {tab === 'directory' ? (
        <Card pad={false}>
          <div style={{ padding: '16px 20px 0' }}>
            <Toolbar>
              <SearchInput value={q} onChange={setQ} placeholder="Search name, unit, skill…" />
              <SelectFilter label="Role" value={role} onChange={setRole} options={['All roles', 'Head karigar', 'Karigar', 'Subcontractor']} />
            </Toolbar>
          </div>
          <DataTable<Party>
            caption="Karigar directory"
            rows={rows}
            rowKey={(r) => r.id}
            onRowClick={(r) => navigate('karigars', r.id)}
            initialSort={{ key: 'custody', dir: 'desc' }}
            columns={[
              {
                key: 'name',
                header: 'Name',
                sort: (r) => r.name,
                render: (r) => (
                  <span className="profile" style={{ gap: 10, flexWrap: 'nowrap' }}>
                    <span className="avatar">{initials(r.name)}</span>
                    <span className="cell-main">
                      <b>{r.name}</b>
                      <small className="mono">{r.id}</small>
                    </span>
                  </span>
                ),
              },
              { key: 'role', header: 'Role', sort: (r) => r.role, render: (r) => <Pill tone={r.role === 'Head karigar' ? 'gold' : 'muted'}>{r.role}</Pill> },
              { key: 'reports', header: 'Reports to', hideSm: true, render: (r) => (r.parentId === VAULT ? 'Manufacturer' : s.parties.find((p) => p.id === r.parentId)?.name) },
              { key: 'unit', header: 'Unit', hideSm: true, sort: (r) => r.unit, render: (r) => r.unit },
              { key: 'jobs', header: 'Jobs', align: 'right', sort: (r) => activeJobs(r.id), render: (r) => activeJobs(r.id) },
              { key: 'custody', header: 'In custody (fine)', align: 'right', sort: (r) => hold.get(r.id) ?? 0, render: (r) => <span className="mono">{g3(hold.get(r.id) ?? 0)}</span> },
            ]}
          />
        </Card>
      ) : (
        <Card title="Custody hierarchy">
          <Tree parentId={VAULT} parties={s.parties} hold={hold} root />
        </Card>
      )}
    </div>
  );
}

function Tree({ parentId, parties, hold, root }: { parentId: string; parties: Party[]; hold: Map<string, number>; root?: boolean }) {
  const self = parties.find((p) => p.id === parentId)!;
  const kids = parties.filter((p) => p.parentId === parentId);
  const node = (
    <a className="tree-node" href={self.id === VAULT ? undefined : `#/app/karigars/${self.id}`}>
      <span className="avatar">{self.id === VAULT ? 'AT' : initials(self.name)}</span>
      <span className="cell-main">
        <b>{self.name}</b>
        <small>{self.role}</small>
      </span>
      {self.id !== VAULT && <span className="mono muted">{g3(hold.get(self.id) ?? 0)}</span>}
    </a>
  );
  if (root)
    return (
      <ul className="tree tree-root">
        <li>
          {node}
          {kids.length > 0 && <Branch kids={kids} parties={parties} hold={hold} />}
        </li>
      </ul>
    );
  return (
    <>
      {node}
      {kids.length > 0 && <Branch kids={kids} parties={parties} hold={hold} />}
    </>
  );
}

function Branch({ kids, parties, hold }: { kids: Party[]; parties: Party[]; hold: Map<string, number> }) {
  return (
    <ul className="tree">
      {kids.map((k) => (
        <li key={k.id}>
          <Tree parentId={k.id} parties={parties} hold={hold} />
        </li>
      ))}
    </ul>
  );
}

function Profile({ id }: { id: string }) {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const p = s.parties.find((x) => x.id === id);
  const ev = useMemo(() => ledger(s).filter((e) => e.from === id || e.to === id), [s, id]);
  const jobIds = [...new Set(ev.map((e) => e.jobId))];
  const perJob = jobIds.map((j) => ({ jobId: j, held: custody(s, j).get(id) ?? 0 }));
  const prod = s.production.filter((x) => x.partyId === id);
  if (!p || p.id === VAULT)
    return (
      <Card>
        <Empty title={`No karigar “${id}”`}>
          <Link to="karigars" className="link">Back to directory</Link>
        </Empty>
      </Card>
    );
  const total = r3(perJob.reduce((a, j) => a + j.held, 0));
  const reports = s.parties.filter((x) => x.parentId === id);
  const finishedGross = r3(s.returns.filter((r) => r.from === id && r.type === 'Finished goods').reduce((a, r) => a + r.gross, 0));

  return (
    <div className="stack">
      <Card>
        <div className="profile">
          <span className="avatar avatar-lg">{initials(p.name)}</span>
          <div style={{ flex: 1, minWidth: 200 }}>
            <h2>{p.name}</h2>
            <span className="muted">
              <span className="mono">{p.id}</span> · {p.role} · {p.unit}
            </span>
          </div>
          <div className="chips">
            {p.skills.map((k) => (
              <Pill key={k} tone="muted">{k}</Pill>
            ))}
          </div>
        </div>
      </Card>

      <div className="kpis">
        <Kpi icon="layers" label="Gold in custody" value={g3(total)} sub="fine, across jobs" />
        <Kpi icon="doc" label="Jobs touched" value={jobIds.length} />
        <Kpi icon="return" label="Finished goods returned" value={g3(finishedGross)} sub="gross" />
        <Kpi icon="shield" label="Labour rate" value={`${inr(p.labourRate)}/g`} sub="of finished goods" />
      </div>

      <div className="grid-2">
        <Card title="Custody by job (fine)" pad={false}>
          <DataTable
            caption={`Custody held by ${p.name} per job`}
            rows={perJob}
            rowKey={(r) => r.jobId}
            onRowClick={(r) => navigate('jobs', r.jobId)}
            columns={[
              { key: 'job', header: 'Job', render: (r) => jobLabel(r.jobId) },
              { key: 'st', header: 'Status', render: (r) => { const j = s.jobs.find((x) => x.id === r.jobId)!; const st = jobStatus(s, j); return <Pill tone={statusTone(st)}>{st}</Pill>; } },
              { key: 'held', header: 'Held', align: 'right', sort: (r) => r.held, render: (r) => <span className="mono">{g3(r.held)}</span> },
            ]}
          />
        </Card>
        <Card title="Hierarchy">
          <KeyValues
            items={[
              ['Reports to', p.parentId === VAULT ? 'Manufacturer (vault)' : <Link to="karigars" id={p.parentId!} className="link">{partyName(p.parentId!)}</Link>],
              ['With the firm since', fmtDate(p.since)],
              ['Team', reports.length ? reports.map((r, i) => (<span key={r.id}>{i ? ', ' : ''}<Link to="karigars" id={r.id} className="link">{r.name}</Link></span>)) : '—'],
            ]}
          />
        </Card>
      </div>

      <div className="grid-2-even">
        <Card title="Custody movements">
          <Timeline
            items={[...ev].reverse().map((e) => ({
              id: e.id,
              date: fmtDate(e.date),
              icon: e.kind === 'Issue' ? 'issue' : e.kind === 'Transfer' ? 'transfer' : 'return',
              title: `${e.kind} ${e.to === id ? 'in from' : 'out to'} ${partyName(e.to === id ? e.from : e.to)}`,
              meta: `${e.id} · ${e.jobId}`,
              value: `${e.to === id ? '+' : '−'}${g3(e.fine)}`,
            }))}
          />
        </Card>
        <Card title="Production work" pad={false}>
          <DataTable
            caption={`Production entries for ${p.name}`}
            rows={prod}
            rowKey={(r) => r.id}
            empty="No production entries."
            columns={[
              { key: 'd', header: 'Date', sort: (r) => r.date, render: (r) => fmtDate(r.date) },
              { key: 'j', header: 'Job', render: (r) => <Link to="jobs" id={r.jobId} className="link mono">{r.jobId}</Link> },
              { key: 's', header: 'Stage', render: (r) => r.stage },
              { key: 'st', header: 'Status', render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
