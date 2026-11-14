import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import { Icon, IconDefs } from '../components/Icon';
import { Logo } from '../components/Nav';
import { PAGES, href, navigate, useRoute, type PageKey } from './router';
import { useAppState, resetDemo, syncWithBackend } from './data/store';
import { AS_OF } from './data/seed';
import { fmtDate } from './data/calc';
import { subscribeApiState, getApiState, logout, checkAuth, type ApiState } from './data/api';
import { Login } from './pages/Login';
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

function Topbar({
  onMenu,
  onLogout,
  onExitDemo,
}: {
  onMenu: () => void;
  onLogout?: () => void;
  onExitDemo?: () => void;
}) {
  const { page, id } = useRoute();
  const s = useAppState();
  const [apiState, setApiState] = useState<ApiState>(getApiState());

  useEffect(() => {
    return subscribeApiState(setApiState);
  }, []);

  const localActions = s.audit.filter((a) => a.source === 'local-demo').length;
  const label = PAGES.find((p) => p.key === page)?.label;

  const chipLabel =
    apiState.status === 'connected'
      ? `Live API · ${apiState.user?.fullName || 'Admin'}`
      : apiState.status === 'connecting'
      ? 'Connecting to API…'
      : 'Demo offline fallback';

  const chipTitle =
    apiState.status === 'connected'
      ? `Connected to authoritative backend ledger at ${apiState.url}`
      : `No API connected (${apiState.url}). Showing synthetic seed data.`;

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
        <span
          className={`tb-chip ${apiState.status === 'connected' ? 'tb-chip-live' : ''}`}
          title={chipTitle}
          onClick={() => syncWithBackend()}
          style={{ cursor: 'pointer' }}
        >
          <i
            className="tb-dot"
            aria-hidden="true"
            style={{
              backgroundColor:
                apiState.status === 'connected'
                  ? '#10b981'
                  : apiState.status === 'connecting'
                  ? '#f59e0b'
                  : '#94a3b8',
            }}
          />
          <span className="tb-chip-text">{chipLabel}</span>
        </span>
        <span className="tb-chip tb-hide-sm">As of {fmtDate(AS_OF)}</span>
        {localActions > 0 && (
          <button className="tb-chip tb-reset" onClick={resetDemo} title="Discard all actions taken in this browser session">
            {localActions} local change{localActions === 1 ? '' : 's'} · Reset
          </button>
        )}
        {apiState.authenticated ? (
          <button
            className="tb-chip tb-signout"
            onClick={onLogout}
            title="Sign out of authoritative backend ledger"
            style={{ cursor: 'pointer' }}
          >
            <Icon name="arrow" size={13} style={{ transform: 'rotate(180deg)' }} />
            <span>Sign Out</span>
          </button>
        ) : (
          <button
            className="tb-chip tb-signin"
            onClick={onExitDemo}
            title="Sign in to live backend ledger"
            style={{ cursor: 'pointer', background: 'rgba(226, 179, 92, 0.15)', borderColor: 'rgba(226, 179, 92, 0.4)' }}
          >
            <Icon name="check" size={13} />
            <span>Sign In</span>
          </button>
        )}
      </div>
    </header>
  );
}

export default function AppShell() {
  const { page, id } = useRoute();
  const [menu, setMenu] = useState(false);
  const [apiState, setApiState] = useState<ApiState>(getApiState());
  const [demoMode, setDemoMode] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('aurumtrace_demo_mode') === 'true';
    }
    return false;
  });

  const main = useRef<HTMLElement>(null);
  const View = VIEWS[page];

  useEffect(() => {
    checkAuth();
    return subscribeApiState(setApiState);
  }, []);

  useEffect(() => {
    const landingTitle = document.title.includes('·') ? 'AURUMTRACE — Precious-Metal Intelligence Platform' : document.title;
    return () => {
      document.title = landingTitle;
    };
  }, []);

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menu]);

  useEffect(() => {
    document.title = `${PAGES.find((p) => p.key === page)?.label ?? 'App'} · AURUMTRACE`;
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [page, id]);

  const handleLogout = () => {
    logout();
    setDemoMode(false);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('aurumtrace_demo_mode');
    }
  };

  const handleExitDemo = () => {
    setDemoMode(false);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('aurumtrace_demo_mode');
    }
  };

  // If not authenticated and user hasn't explicitly chosen offline demo mode, display Login screen
  if (!apiState.authenticated && !demoMode) {
    return (
      <div className="app">
        <IconDefs />
        <Login
          onSuccess={() => {
            setDemoMode(false);
            if (typeof window !== 'undefined') {
              localStorage.removeItem('aurumtrace_demo_mode');
            }
          }}
          onExploreDemo={() => {
            setDemoMode(true);
            if (typeof window !== 'undefined') {
              localStorage.setItem('aurumtrace_demo_mode', 'true');
            }
          }}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <IconDefs />
      <Sidebar open={menu} onClose={() => setMenu(false)} />
      <div className="app-main">
        <Topbar
          onMenu={() => setMenu(true)}
          onLogout={handleLogout}
          onExitDemo={handleExitDemo}
        />
        <main ref={main} className="app-content" tabIndex={-1}>
          <View id={id} />
        </main>
      </div>
    </div>
  );
}
