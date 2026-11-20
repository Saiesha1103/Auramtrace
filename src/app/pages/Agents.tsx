import { useCallback, useEffect, useMemo, useState } from 'react';
import { agentsApi, isLiveApi, type AgentRun, type AgentTraceStep, type TrackRecord, type WorksheetDto } from '../data/api';
import { Btn, Card, DataTable, Empty, FormMessage, Kpi, PageHeader, Pill, Tabs, type Tone } from '../ui';

const SEV: Record<string, Tone> = { critical: 'alert', high: 'warn', medium: 'muted' };
const inr = (n: number) => `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Shows each step of an agent run: which read-only tool it called, with what, and what came back. */
export function AgentTrace({ trace }: { trace: AgentTraceStep[] }) {
  if (!trace?.length) return null;
  return (
    <ol className="agent-trace">
      {trace.map((t, i) => (
        <li key={i} className={`agent-step ${t.ok === false ? 'is-err' : ''}`}>
          <span className="agent-step-n">{t.step ?? '·'}</span>
          {t.type === 'tool_call' ? (
            <span>
              <code>{t.tool}</code>
              <small className="muted"> ({Object.entries(t.args ?? {}).map(([k, v]) => `${k}=${String(v).slice(0, 8)}${String(v).length > 8 ? '…' : ''}`).join(', ')})</small>
              <small> → {t.ok ? t.summary : <span className="alert-text">{t.error}</span>}</small>
            </span>
          ) : t.type === 'final' ? (
            <span>
              <b>Final answer</b> <small className="muted">{t.ok ? 'composed from observed records' : 'unusable'}</small>
            </span>
          ) : (
            <span className="alert-text">LLM unavailable ({t.error}); switched to the rule-based planner</span>
          )}
        </li>
      ))}
    </ol>
  );
}

type Tab = 'watch' | 'investigate' | 'payments' | 'record';

export function Agents() {
  const live = isLiveApi();
  const [tab, setTab] = useState<Tab>('watch');
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [exceptions, setExceptions] = useState<any[]>([]);
  const [inv, setInv] = useState<any | null>(null);
  const [sheets, setSheets] = useState<WorksheetDto[]>([]);
  const [karigars, setKarigars] = useState<{ id: string; code: string; name: string }[]>([]);
  const [records, setRecords] = useState<TrackRecord[]>([]);
  const [copied, setCopied] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!live) return;
    try {
      const [runs, ex, ws, ks] = await Promise.all([agentsApi.runs(), agentsApi.exceptions(), agentsApi.worksheets(), agentsApi.karigars()]);
      setRun((r) => r ?? runs.items[0] ?? null);
      setExceptions(ex.items);
      setSheets(ws.items);
      setKarigars(ks.items);
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
  }, [live]);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (tab !== 'record' || !karigars.length || records.length) return;
    Promise.all(karigars.map((k) => agentsApi.trackRecord(k.id))).then(setRecords).catch((e) => setMsg({ ok: false, text: e.message }));
  }, [tab, karigars, records.length]);

  const kName = useMemo(() => Object.fromEntries(karigars.map((k) => [k.id, `${k.name} (${k.code})`])), [karigars]);

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
    setBusy(false);
  };

  if (!live) {
    return (
      <div className="stack">
        <PageHeader eyebrow="Control" title="AI Agents" />
        <Card title="Live backend required">
          <p className="muted">The agents read the authoritative ledger on the server. Sign in to the live API to run them; the offline demo has no agent runtime.</p>
        </Card>
      </div>
    );
  }

  const unpaid = sheets.filter((s) => ['approved', 'karigar_accepted', 'disputed'].includes(s.status));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Control · agentic AI"
        title="AI Agents"
        lede="Agents plan their own steps over read-only tools, and every step is shown. They propose; people decide. No agent can move gold, approve a settlement or send a message."
      />
      <Tabs<Tab>
        label="Agents"
        value={tab}
        onChange={setTab}
        tabs={[
          { key: 'watch', label: 'Deadline & payment watcher' },
          { key: 'investigate', label: 'Investigation agent', count: exceptions.filter((e) => e.status !== 'resolved' && e.status !== 'dismissed').length },
          { key: 'payments', label: 'Karigar payments', count: unpaid.length },
          { key: 'record', label: 'Track records' },
        ]}
      />
      <FormMessage result={msg} />

      {tab === 'watch' && (
        <>
          <Card
            title="Today's check"
            actions={<Btn variant="gold" icon="sparkle" disabled={busy} onClick={() => act(async () => setRun(await agentsApi.watch(7)))}>{busy ? 'Agent running…' : 'Run watcher agent'}</Btn>}
          >
            {run ? (
              <>
                <p style={{ marginTop: 0 }}>{run.output.summary}</p>
                <p className="muted small">
                  Planner <b>{run.provider}</b> · {run.output.agent.toolCalls} tool call(s) · {new Date(run.createdAt).toLocaleString('en-IN')}
                </p>
              </>
            ) : (
              <Empty title="No runs yet">Run the agent to check deadlines, customer occasion dates and unpaid karigars.</Empty>
            )}
          </Card>
          {run && (
            <div className="grid-2-even">
              <Card title={`Alerts (${run.output.alerts.length})`}>
                {run.output.alerts.length ? (
                  <ul className="list-plain">
                    {run.output.alerts.map((a, i) => (
                      <li key={i} className="doc-item">
                        <span>
                          <Pill tone={SEV[a.severity]} icon={null}>{a.severity}</Pill> <b>{a.title}</b>
                        </span>
                        <small>{a.detail}</small>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty title="Nothing at risk" />
                )}
              </Card>
              <Card title="Draft messages" actions={<Pill tone="muted" icon={null}>Not sent · review first</Pill>}>
                {run.output.draftMessages.length ? (
                  <ul className="list-plain">
                    {run.output.draftMessages.map((d, i) => (
                      <li key={i} className="draft-msg">
                        <small className="muted">
                          To {d.audience}
                          {d.karigarId && kName[d.karigarId] ? ` · ${kName[d.karigarId]}` : ''} · {d.channel}
                        </small>
                        <p>{d.text}</p>
                        <Btn
                          size="sm"
                          icon="doc"
                          onClick={() => {
                            navigator.clipboard?.writeText(d.text);
                            setCopied(i);
                          }}
                        >
                          {copied === i ? 'Copied' : 'Copy'}
                        </Btn>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty title="No drafts" />
                )}
              </Card>
            </div>
          )}
          {run && (
            <Card title="What the agent did">
              <AgentTrace trace={run.trace} />
            </Card>
          )}
        </>
      )}

      {tab === 'investigate' && (
        <>
          <Card
            title="Exception cases on the server"
            actions={<Btn icon="search" disabled={busy} onClick={() => act(async () => { await agentsApi.detect(); await load(); })}>Scan for exceptions</Btn>}
          >
            <DataTable
              rows={exceptions}
              rowKey={(e: any) => e.id}
              empty="No exception cases. Run a scan after reconciling jobs."
              columns={[
                { key: 'c', header: 'Case', render: (e: any) => <b className="mono">{e.code}</b> },
                { key: 't', header: 'Type', render: (e: any) => e.exceptionType.replace(/_/g, ' ') },
                { key: 's', header: 'Severity', render: (e: any) => <Pill tone={statusTone2(e.severity)} icon={null}>{e.severity}</Pill> },
                { key: 'st', header: 'Status', render: (e: any) => e.status },
                {
                  key: 'a',
                  header: '',
                  render: (e: any) => (
                    <Btn size="sm" icon="sparkle" disabled={busy} onClick={() => act(async () => setInv(await agentsApi.investigate(e.id)))}>
                      Investigate
                    </Btn>
                  ),
                },
              ]}
            />
          </Card>
          {inv && (
            <div className="grid-2-even">
              <Card title="Findings" actions={<Pill tone="gold" icon={null}>{inv.provider}</Pill>}>
                <p style={{ marginTop: 0 }}>{inv.response.summary}</p>
                <h4 className="small">Verified facts (each cites a record the agent read)</h4>
                <ul className="rule-list">
                  {inv.response.verifiedFacts.map((f: any, i: number) => (
                    <li key={i}>
                      <span>{f.fact}</span>
                      <b className="mono small">{String(f.recordId).slice(0, 8)}</b>
                    </li>
                  ))}
                </ul>
                {inv.response.suspectedCauses?.length > 0 && (
                  <>
                    <h4 className="small">Suspected causes</h4>
                    <ul className="rule-list">
                      {inv.response.suspectedCauses.map((c: any, i: number) => (
                        <li key={i}>
                          <span>
                            <b>{c.cause}</b> — {c.rationale}
                          </span>
                          <b>{Math.round((c.probability ?? 0) * 100)}%</b>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {inv.response.recommendedActions?.length > 0 && (
                  <>
                    <h4 className="small">Recommended (for a person to decide)</h4>
                    <ul className="rule-list">
                      {inv.response.recommendedActions.map((a: any, i: number) => (
                        <li key={i}>
                          <span>{a.action}</span>
                          <b>{a.role}</b>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </Card>
              <Card title={`Agent steps (${inv.response.agent?.toolCalls ?? 0} tool calls)`}>
                <AgentTrace trace={inv.response.agentTrace} />
              </Card>
            </div>
          )}
        </>
      )}

      {tab === 'payments' && (
        <Card title="Settlements awaiting the karigar or payment">
          <DataTable
            rows={unpaid}
            rowKey={(s) => s.id}
            empty="No karigar is waiting on a settlement."
            columns={[
              { key: 'c', header: 'Worksheet', render: (s) => <b className="mono">{s.code}</b> },
              { key: 'k', header: 'Karigar', render: (s) => kName[s.karigarId] ?? s.karigarId.slice(0, 8) },
              { key: 'a', header: 'Net payable', render: (s) => inr(s.netPayableAmount), align: 'right' },
              {
                key: 's',
                header: 'Status',
                render: (s) => (
                  <Pill tone={s.status === 'disputed' ? 'alert' : s.status === 'approved' ? 'warn' : 'gold'} icon={null}>
                    {s.status === 'approved' ? 'awaiting karigar' : s.status === 'karigar_accepted' ? 'agreed · pay now' : 'disputed'}
                  </Pill>
                ),
              },
              { key: 'd', header: 'Days since approval', render: (s) => (s.approvedAt ? Math.floor((Date.now() - new Date(s.approvedAt).getTime()) / 86_400_000) : '—'), align: 'right' },
              { key: 'r', header: 'Karigar note', render: (s) => s.disputeReason ?? '', hideSm: true },
              {
                key: 'p',
                header: '',
                render: (s) =>
                  s.status === 'karigar_accepted' ? (
                    <Btn
                      size="sm"
                      variant="gold"
                      disabled={busy}
                      onClick={() => {
                        const ref = window.prompt(`Payment reference for ${s.code} (UPI / bank / cash slip):`);
                        if (ref && ref.trim().length >= 2) act(async () => { await agentsApi.markPaid(s.id, ref.trim()); setMsg({ ok: true, text: `${s.code} recorded as paid.` }); await load(); });
                      }}
                    >
                      Record payment
                    </Btn>
                  ) : null,
              },
            ]}
          />
        </Card>
      )}

      {tab === 'record' && (
        <Card title="Karigar track records" actions={<Pill tone="muted" icon={null}>Derived from the ledger</Pill>}>
          {records.length ? (
            <>
              <div className="kpis" style={{ marginBottom: 16 }}>
                <Kpi label="Karigars" value={records.length} icon="user" />
                <Kpi label="Delivered jobs" value={records.reduce((n, r) => n + r.jobsDelivered, 0)} icon="check" />
                <Kpi label="Waiting for payment" value={records.reduce((n, r) => n + r.awaitingPayment.length, 0)} icon="clock" />
              </div>
              <DataTable
                rows={records}
                rowKey={(r) => r.karigarId}
                columns={[
                  { key: 'n', header: 'Karigar', render: (r) => `${r.name} (${r.code})`, sort: (r) => r.name },
                  { key: 'd', header: 'Delivered', render: (r) => `${r.jobsDelivered}/${r.jobsTotal}`, align: 'right' },
                  { key: 'o', header: 'On time', render: (r) => (r.onTimeRatePct == null ? '—' : `${r.onTimeRatePct}%`), align: 'right', sort: (r) => r.onTimeRatePct ?? -1 },
                  { key: 'w', header: 'Within wastage', render: (r) => (r.withinAllowanceRatePct == null ? '—' : `${r.withinAllowanceRatePct}%`), align: 'right', sort: (r) => r.withinAllowanceRatePct ?? -1 },
                  { key: 'x', header: 'Disputes', render: (r) => r.settlementsDisputed, align: 'right' },
                  { key: 'p', header: 'Avg days to pay', render: (r) => r.averageDaysToPayment ?? '—', align: 'right' },
                  { key: 'g', header: 'Gold held', render: (r) => `${r.fineGoldHeldG.toFixed(3)} g`, align: 'right', hideSm: true },
                ]}
              />
            </>
          ) : (
            <p className="muted">Loading track records…</p>
          )}
        </Card>
      )}
    </div>
  );
}

function statusTone2(sev: string): Tone {
  return sev === 'critical' || sev === 'high' ? 'alert' : sev === 'medium' ? 'warn' : 'muted';
}
