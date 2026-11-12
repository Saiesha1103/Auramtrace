import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import { Icon, IconDefs } from '../components/Icon';
import { Logo } from '../components/Nav';
import { PAGES, href, navigate, useRoute, type PageKey } from './router';
import { useAppState, resetDemo } from './data/store';
import { AS_OF } from './data/seed';
import { fmtDate } from './data/calc';
import { DATA_SOURCE_NOTE } from './data/api';
import { Dashboard } from './pages/Dashboard';
import { Karigars } from './pages/Karigars';
import { Jobs } from './pages/Jobs';
import { Issuance } from './pages/Issuance';
import { Transfers } from './pages/Transfers';
import { Production } from './pages/Production';
import { Returns } from './pages/Returns';
import { Reconciliation } from './pages/Reconciliation';
import { Investigation } from './pages/Investigation';
import { Settlement } from './pages/Settlement';
import { Reports } from './pages/Reports';
import './app.css';

const VIEWS: Record<PageKey, ComponentType<{ id?: string }>> = {
  dashboard: Dashboard,
  karigars: Karigars,
  jobs: Jobs,
  issuance: Issuance,
  transfers: Transfers,
  production: Production,
  returns: Returns,
  reconciliation: Reconciliation,
  investigation: Investigation,
  settlement: Settlement,
  reports: Reports,
};

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { page } = useRoute();
  const groups = ['Overview', 'Custody', 'Control'] as const;
  return (
    <>
      <div className={`sb-scrim ${open ? 'is-on' : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sb ${open ? 'is-open' : ''}`} aria-label="Main navigation">
        <a className="sb-brand" href={href('dashboard')} onClick={onClose}>
          <Logo />
        </a>
        <nav className="sb-nav">
          {groups.map((g) => (
            <div key={g} className="sb-group">
              <span className="sb-group-label">{g}</span>
              {PAGES.filter((p) => p.group === g).map((p) => (
                <a key={p.key} href={href(p.key)} className={`sb-link ${page === p.key ? 'is-on' : ''}`} aria-current={page === p.key ? 'page' : undefined} onClick={onClose}>
                  <Icon name={p.icon} size={18} />
                  {p.label}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="sb-foot">
          <a className="sb-back" href="#top">
            <Icon name="arrow" size={14} style={{ transform: 'scaleX(-1)' }} />
            Back to website
          </a>
        </div>
      </aside>
    </>
  );
}

function QuickSearch() {
  const s = useAppState();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    const jobs = s.jobs.filter((j) => `${j.id} ${j.title} ${j.orderRef}`.toLowerCase().includes(t)).map((j) => ({ key: j.id, label: `${j.id} · ${j.title}`, kind: 'Job', go: () => navigate('jobs', j.id) }));
    const people = s.parties.filter((p) => p.id !== 'VAULT' && `${p.id} ${p.name}`.toLowerCase().includes(t)).map((p) => ({ key: p.id, label: `${p.name} (${p.id})`, kind: p.role, go: () => navigate('karigars', p.id) }));
    return [...jobs, ...people].slice(0, 7);
  }, [q, s.jobs, s.parties]);
  const pick = (r: (typeof results)[number]) => {
    r.go();
    setQ('');
    setOpen(false);
  };
  return (
    <div className="qs">
      <label className="search">
        <Icon name="search" size={16} />
        <span className="sr-only">Search jobs and karigars</span>
        <input
          type="search"
          value={q}
          placeholder="Search jobs, karigars…"
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => e.key === 'Enter' && results[0] && pick(results[0])}
          aria-autocomplete="list"
          aria-expanded={open && results.length > 0}
        />
      </label>
      {open && results.length > 0 && (
        <ul className="qs-list" role="listbox">
          {results.map((r) => (
            <li key={r.key} role="option" aria-selected="false" onMouseDown={() => pick(r)}>
              <span>{r.label}</span>
              <small>{r.kind}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const { page, id } = useRoute();
  const s = useAppState();
  const localActions = s.audit.filter((a) => a.source === 'local-demo').length;
  const label = PAGES.find((p) => p.key === page)?.label;
  return (
    <header className="tb">
      <button className="icon-btn tb-menu" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" size={20} />
      </button>
      <nav className="tb-crumbs" aria-label="Breadcrumb">
        <a href={href(page)}>{label}</a>
        {id && (
          <>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{id}</span>
          </>
        )}
      </nav>
      <QuickSearch />
      <div className="tb-right">
        <span className="tb-chip" title={DATA_SOURCE_NOTE}>
          <i className="tb-dot" aria-hidden="true" />
          <span className="tb-chip-text">{DATA_SOURCE_NOTE}</span>
        </span>
        <span className="tb-chip tb-hide-sm">As of {fmtDate(AS_OF)}</span>
        {localActions > 0 && (
          <button className="tb-chip tb-reset" onClick={resetDemo} title="Discard all actions taken in this browser session">
            {localActions} local change{localActions === 1 ? '' : 's'} · Reset
          </button>
        )}
      </div>
    </header>
  );
}

export default function AppShell() {
  const { page, id } = useRoute();
  const [menu, setMenu] = useState(false);
  const main = useRef<HTMLElement>(null);
  const View = VIEWS[page];

  useEffect(() => {
    document.title = `${PAGES.find((p) => p.key === page)?.label ?? 'App'} · AURUMTRACE`;
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [page, id]);

  return (
    <div className="app">
      <IconDefs />
      <Sidebar open={menu} onClose={() => setMenu(false)} />
      <div className="app-main">
        <Topbar onMenu={() => setMenu(true)} />
        <main ref={main} className="app-content" tabIndex={-1}>
          <View id={id} />
        </main>
      </div>
    </div>
  );
}
