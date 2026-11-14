import { useMemo, useState } from 'react';
import { setExceptionReview, useAppState } from '../data/store';
import { AS_OF } from '../data/seed';
import { daysBetween, exceptions, fmtDate, g3, ledger, pct, r3, reconcile, type ExceptionItem } from '../data/calc';
import { requestAiExplanation } from '../data/api';
import { useLookups } from '../lookups';
import { Link, navigate } from '../router';
import { Btn, Card, DataTable, Empty, FormMessage, KeyValues, Kpi, PageHeader, Pill, SelectFilter, Timeline, Toolbar, statusTone, type TimelineItem } from '../ui';
import { Icon } from '../../components/Icon';

export function Investigation({ id }: { id?: string }) {
  const s = useAppState();
  const all = useMemo(() => exceptions(s), [s]);
  if (id) {
    const ex = all.find((e) => e.id === id);
    return ex ? <Case ex={ex} /> : (
      <Card>
        <Empty title={`No open exception “${id}”`}>
          It may have been cleared by newer data. <Link to="investigation" className="link">All exceptions</Link>
        </Empty>
      </Card>
    );
  }
  return <Queue all={all} />;
}

function Queue({ all }: { all: ExceptionItem[] }) {
  const s = useAppState();
  const { jobLabel } = useLookups();
  const [sev, setSev] = useState('All');
  const [kind, setKind] = useState('All kinds');
  const [review, setReview] = useState('Not resolved');
  const reviewOf = (e: ExceptionItem) => s.exceptionReview[e.id] ?? 'Open';
  const rows = all.filter((e) => (sev === 'All' || e.severity === sev) && (kind === 'All kinds' || e.kind === kind) && (review === 'All' || (review === 'Not resolved' ? reviewOf(e) !== 'Resolved' : reviewOf(e) === review)));
  return (
    <div className="stack">
      <PageHeader eyebrow="Control" title="AI Investigation" lede="Exceptions raised by reconciliation and custody rules, each with its events and evidence assembled for review." />
      <div className="kpis">
        <Kpi icon="alert" label="Open exceptions" value={all.filter((e) => reviewOf(e) !== 'Resolved').length} tone="alert" />
        <Kpi icon="scale" label="Variance cases" value={all.filter((e) => e.kind === 'Variance').length} />
        <Kpi icon="doc" label="Evidence documents" value={s.evidence.length} />
        <Kpi icon="sparkle" label="AI explanations" value="Not connected" sub="no AI service configured" />
      </div>
      <Card pad={false}>
        <div style={{ padding: '16px 20px 0' }}>
          <Toolbar>
            <SelectFilter label="Severity" value={sev} onChange={setSev} options={['All', 'High', 'Medium', 'Low']} />
            <SelectFilter label="Kind" value={kind} onChange={setKind} options={['All kinds', 'Variance', 'Purity mismatch', 'Unacknowledged lot', 'Overdue job']} />
            <SelectFilter label="Review" value={review} onChange={setReview} options={['Not resolved', 'Open', 'Under review', 'Resolved', 'All']} />
          </Toolbar>
        </div>
        <DataTable<ExceptionItem>
          caption="Exceptions"
          rows={rows}
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate('investigation', r.id)}
          columns={[
            { key: 'id', header: 'Exception', sort: (r) => r.id, render: (r) => <span className="cell-main"><b className="mono">{r.id}</b><small>{r.kind}</small></span> },
            { key: 'sev', header: 'Severity', sort: (r) => ({ High: 0, Medium: 1, Low: 2 })[r.severity], render: (r) => <Pill tone={statusTone(r.severity)}>{r.severity}</Pill> },
            { key: 'job', header: 'Job', hideSm: true, render: (r) => jobLabel(r.jobId) },
            { key: 'sum', header: 'Summary', render: (r) => <span style={{ whiteSpace: 'normal' }}>{r.summary}</span> },
            { key: 'amt', header: 'Amount (fine)', align: 'right', sort: (r) => r.amountFine ?? -1, render: (r) => <span className="mono">{r.amountFine === null ? '—' : g3(r.amountFine)}</span> },
            { key: 'rev', header: 'Review', render: (r) => <Pill tone={statusTone(reviewOf(r))}>{reviewOf(r)}</Pill> },
          ]}
        />
      </Card>
    </div>
  );
}

function Case({ ex }: { ex: ExceptionItem }) {
  const s = useAppState();
  const { partyName, jobLabel } = useLookups();
  const job = s.jobs.find((j) => j.id === ex.jobId)!;
  const rec = reconcile(s, job);
  const review = s.exceptionReview[ex.id] ?? 'Open';
  const [ai, setAi] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const timeline: TimelineItem[] = useMemo(() => {
    const ev = ledger(s)
      .filter((e) => e.jobId === job.id)
      .map((e) => {
        const ret = e.kind === 'Return' ? s.returns.find((r) => r.id === e.id) : undefined;
        const flag = !!ret && ret.assayedFineness !== undefined && ret.assayedFineness < ret.declaredFineness - 0.02;
        return {
          sort: e.date + e.id,
          item: {
            id: e.id,
            date: fmtDate(e.date),
            icon: (e.kind === 'Issue' ? 'issue' : e.kind === 'Transfer' ? 'transfer' : 'return') as TimelineItem['icon'],
            title: `${e.kind}: ${partyName(e.from)} → ${partyName(e.to)}`,
            meta: `${e.id} · ${e.detail}${flag && ret ? ` · declared ${pct(ret.declaredFineness)}, assayed ${pct(ret.assayedFineness!)}` : ''}`,
            value: g3(e.fine),
            flag,
          },
        };
      });
    const prod = s.production
      .filter((p) => p.jobId === job.id)
      .map((p) => ({
        sort: p.date + p.id,
        item: {
          id: p.id,
          date: fmtDate(p.date),
          icon: 'manufacture' as const,
          title: `${p.stage} · ${partyName(p.partyId)}`,
          meta: p.status === 'Done' ? `${p.inGross.toFixed(3)} → ${p.outGross.toFixed(3)} g` : 'in progress',
          value: p.status === 'Done' && p.stage !== 'Alloying' ? `−${r3(p.inGross - p.outGross).toFixed(3)} g` : undefined,
        },
      }));
    return [...ev, ...prod].sort((a, b) => a.sort.localeCompare(b.sort)).map((x) => x.item);
  }, [s, job.id, partyName]);

  const docs = s.evidence.filter((d) => d.jobId === job.id);

  // deterministic rule checks — arithmetic on recorded data only
  const findings = useMemo(() => {
    const out: { text: string; value?: string }[] = [];
    if (ex.kind === 'Variance' || ex.kind === 'Purity mismatch') {
      out.push({ text: `Fine issued ${g3(rec.issuedFine)}, returned ${g3(rec.returnedFine)}; variance ${g3(rec.varianceFine)} against allowance ${g3(rec.allowanceFine)} (${job.lossAllowancePct}%).`, value: g3(rec.unexplainedFine) });
      if (rec.purityShortfallFine > 0) {
        const covered = r3(Math.min(rec.purityShortfallFine, rec.unexplainedFine || rec.purityShortfallFine));
        out.push({ text: `Assay shortfall on returns (declared − assayed purity × gross) totals ${g3(rec.purityShortfallFine)}. Arithmetically this accounts for ${g3(covered)} of the unexplained amount.`, value: g3(covered) });
        if (rec.unexplainedFine > covered) out.push({ text: 'Amount not accounted for by recorded purity shortfalls.', value: g3(r3(rec.unexplainedFine - covered)) });
      }
      const measured = r3(s.production.filter((p) => p.jobId === job.id && p.status === 'Done' && p.stage !== 'Alloying').reduce((a, p) => a + (p.inGross - p.outGross), 0));
      if (measured) out.push({ text: `Stage-by-stage measured process loss: ${g3(measured)} gross ≈ ${g3(r3(measured * job.fineness))} fine at ${pct(job.fineness)} (losses are often partly recovered in scrap and dust).` });
      const cal = docs.find((d) => d.kind === 'Calibration log');
      if (cal) out.push({ text: `Linked calibration record: ${cal.detail}` });
    }
    if (ex.kind === 'Unacknowledged lot') {
      const lot = s.lots.find((l) => l.jobId === job.id && !l.acknowledged);
      if (lot) out.push({ text: `${lot.id} issued to ${partyName(lot.issuedTo)} on ${fmtDate(lot.date)}; no signed receipt after ${daysBetween(lot.date, AS_OF)} days.`, value: g3(r3(lot.gross * lot.fineness)) });
    }
    if (ex.kind === 'Overdue job') {
      const last = [...s.production.filter((p) => p.jobId === job.id)].sort((a, b) => a.date.localeCompare(b.date)).pop();
      out.push({ text: `Deadline ${fmtDate(job.deadline)}; latest recorded stage: ${last ? `${last.stage} (${last.status}) on ${fmtDate(last.date)}` : 'none'}.` });
    }
    return out;
  }, [ex, rec, job, s, docs, partyName]);

  const askAi = async () => {
    setBusy(true);
    const res = await requestAiExplanation(ex.id);
    setAi({ ok: res.ok, text: res.ok ? (res.text || 'Investigation completed.') : (res.error || 'Failed to generate explanation.') });
    setBusy(false);
  };
  const setReview = (st: 'Open' | 'Under review' | 'Resolved') => {
    setExceptionReview(ex.id, job.id, st);
    setNote({ ok: true, text: `Marked ${st.toLowerCase()} in this browser session only (local demo — not sent to any server).` });
  };

  return (
    <div className="stack">
      <PageHeader
        eyebrow={`${ex.kind} · raised ${fmtDate(ex.raised)}`}
        title={`Case ${ex.id}`}
        lede={<>{jobLabel(job.id)} — {ex.summary}</>}
        actions={
          <>
            <Pill tone={statusTone(ex.severity)}>{ex.severity}</Pill>
            <Pill tone={statusTone(review)}>{review}</Pill>
            <Btn icon="scale" onClick={() => navigate('reconciliation', job.id)}>Reconciliation</Btn>
          </>
        }
      />

      <div className="grid-2">
        <Card title="Event timeline">
          <Timeline items={timeline} />
        </Card>
        <div className="stack">
          <Card title="Linked evidence">
            {docs.length ? (
              <ul className="list-plain">
                {docs.map((d) => (
                  <li key={d.id} className="doc-item">
                    <Icon name={d.kind === 'Assay report' ? 'scan' : d.kind === 'Calibration log' ? 'clock' : 'doc'} size={16} />
                    <span>
                      <b className="mono">{d.id}</b> · {d.title}
                    </span>
                    <small>
                      {d.kind} · {fmtDate(d.date)} — {d.detail}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="No documents linked">Synthetic dataset has no evidence for this job.</Empty>
            )}
          </Card>
          <Card title="Job position">
            <KeyValues
              items={[
                ['Issued (fine)', g3(rec.issuedFine)],
                ['Returned (fine)', g3(rec.returnedFine)],
                ['Allowance', g3(rec.allowanceFine)],
                ['Unexplained', <span className={rec.unexplainedFine ? 'alert-text' : ''}>{rec.closed ? g3(rec.unexplainedFine) : 'job open'}</span>],
              ]}
            />
          </Card>
        </div>
      </div>

      <div className="grid-2-even">
        <Card title="Deterministic checks" actions={<Pill tone="muted" icon={null}>Rule-based · not AI</Pill>}>
          {findings.length ? (
            <ul className="rule-list">
              {findings.map((f, i) => (
                <li key={i}>
                  <Icon name="check" size={14} strokeWidth={2} />
                  <span>{f.text}</span>
                  <b>{f.value ?? ''}</b>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No rule findings for this exception" />
          )}
        </Card>
        <Card title="AI explanation" className="ai-panel" actions={<Pill tone="warn">Service not connected</Pill>}>
          <p className="muted" style={{ marginTop: 0 }}>
            An AI explanation would weigh the timeline and evidence and cite them. No AI service is configured for this prototype, so <b>no explanation has been generated</b> and none is shown.
          </p>
          <Btn icon="sparkle" onClick={askAi} disabled={busy}>{busy ? 'Requesting…' : 'Request AI explanation'}</Btn>
          <div style={{ marginTop: 12 }}>
            <FormMessage result={ai} />
          </div>
        </Card>
      </div>

      <Card title="Manager review">
        <div className="row-actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
          <Btn icon="search" onClick={() => setReview('Under review')} disabled={review === 'Under review'}>Mark under review</Btn>
          <Btn variant="gold" icon="check" onClick={() => setReview('Resolved')} disabled={review === 'Resolved'}>Resolve</Btn>
          <Btn variant="quiet" onClick={() => setReview('Open')} disabled={review === 'Open'}>Reopen</Btn>
        </div>
        <div style={{ marginTop: 12 }}>
          <FormMessage result={note} />
        </div>
      </Card>
    </div>
  );
}
