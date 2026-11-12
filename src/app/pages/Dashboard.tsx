import { useMemo } from 'react';
import { useAppState } from '../data/store';
import { AS_OF } from '../data/seed';
import { custody, exceptions, fine, g3, jobStatus, ledger, isOverdue, r3, returnFine, fmtDate } from '../data/calc';
import { useLookups } from '../lookups';
import { Link, navigate } from '../router';
import { BarList, Card, DemoNote, Kpi, LineChart2, PageHeader, Pill, statusTone } from '../ui';

const START = '2026-10-20';

export function Dashboard() {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();

  const data = useMemo(() => {
    const hold = custody(s);
    const out = [...hold.entries()].filter(([, v]) => v > 0.0005).sort((a, b) => b[1] - a[1]);
    const goldOut = r3(out.reduce((a, [, v]) => a + v, 0));
    const month = AS_OF.slice(0, 7);
    const issuedMonth = r3(s.lots.filter((l) => l.date.startsWith(month)).reduce((a, l) => a + fine(l.gross, l.fineness), 0));
    const returnedMonth = r3(s.returns.filter((r) => r.date.startsWith(month)).reduce((a, r) => a + returnFine(r), 0));
    const ex = exceptions(s).filter((e) => s.exceptionReview[e.id] !== 'Resolved');
    const active = s.jobs.filter((j) => ['Issued', 'In production'].includes(jobStatus(s, j)));
    const overdue = s.jobs.filter((j) => isOverdue(s, j));

    // cumulative issued vs returned, day by day
    const days: string[] = [];
    for (let t = Date.parse(START); t <= Date.parse(AS_OF); t += 86400000) days.push(new Date(t).toISOString().slice(0, 10));
    const ev = ledger(s);
    let ci = 0;
    let cr = 0;
    const issued: number[] = [];
    const returned: number[] = [];
    for (const d of days) {
      for (const e of ev) if (e.date === d) e.kind === 'Issue' ? (ci += e.fine) : e.kind === 'Return' ? (cr += e.fine) : null;
      issued.push(r3(ci));
      returned.push(r3(cr));
    }
    const labels = days.map((d) => new Date(d + 'T00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }));
    return { out, goldOut, issuedMonth, returnedMonth, ex, active, overdue, labels, issued, returned };
  }, [s]);

  const recent = [...s.audit].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 8);

  return (
    <div className="stack">
      <PageHeader eyebrow="Manufacturer console" title="Dashboard" lede={`Gold position across every custody level, as of ${fmtDate(AS_OF)}.`} />
      <DemoNote>All figures are synthetic demo data generated for this prototype — no AURUMTRACE API is connected.</DemoNote>

      <div className="kpis">
        <Kpi icon="layers" label="Gold out with karigars" value={g3(data.goldOut)} sub={`${data.out.length} holders · fine`} />
        <Kpi icon="issue" label="Issued this month" value={g3(data.issuedMonth)} sub="fine gold" />
        <Kpi icon="return" label="Returned this month" value={g3(data.returnedMonth)} sub="fine gold" />
        <Kpi icon="manufacture" label="Active jobs" value={data.active.length} sub={`${data.overdue.length} overdue`} tone={data.overdue.length ? 'warn' : undefined} />
        <Kpi icon="alert" label="Open exceptions" value={data.ex.length} sub={`${data.ex.filter((e) => e.severity === 'High').length} high priority`} tone={data.ex.length ? 'alert' : undefined} />
      </div>

      <div className="grid-2">
        <Card title="Gold movement · cumulative fine gold (g)">
          <LineChart2
            labels={data.labels}
            a={{ name: 'Issued', data: data.issued }}
            b={{ name: 'Returned', data: data.returned }}
            unit="g"
            caption="Cumulative fine gold issued versus returned per day, synthetic demo data"
          />
        </Card>
        <Card title="Custody by holder (fine)" actions={<Link to="karigars" className="link">Directory</Link>}>
          <BarList
            items={data.out.map(([id, v]) => ({ key: id, label: <Link to="karigars" id={id} className="link">{partyName(id)}</Link>, value: v }))}
            format={(n) => g3(n)}
          />
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Recent activity" actions={<Link to="reports" query={{ tab: 'audit' }} className="link">Audit history</Link>}>
          <ul className="activity">
            {recent.map((a) => (
              <li key={a.id}>
                <time>{a.at.replace('T', ' ')}</time>
                <span>
                  {a.action}{' '}
                  {a.source === 'local-demo' && <Pill tone="warn" icon={null}>local demo</Pill>}
                </span>
                <small>
                  {a.actor} · {a.target}
                </small>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Needs attention" actions={<Link to="investigation" className="link">All exceptions</Link>}>
          <ul className="list-plain">
            {data.ex.slice(0, 5).map((e) => (
              <li key={e.id}>
                <button className="attn" onClick={() => navigate('investigation', e.id)}>
                  <Pill tone={statusTone(e.severity)}>{e.severity}</Pill>
                  <span className="cell-main">
                    <b>
                      <span className="mono">{e.id}</span> · {e.kind}
                    </b>
                    <small>
                      {jobLabel(e.jobId)} — {e.summary}
                    </small>
                  </span>
                </button>
              </li>
            ))}
            {data.ex.length === 0 && <li className="muted">No open exceptions.</li>}
          </ul>
        </Card>
      </div>
    </div>
  );
}
