import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Icon, type IconName } from '../components/Icon';

/* ------------------------------------------------------------------ layout */

export function PageHeader({ title, eyebrow, lede, actions }: { title: string; eyebrow?: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ph">
      <div className="ph-text">
        {eyebrow && <span className="ph-eyebrow">{eyebrow}</span>}
        <h1 className="ph-title">{title}</h1>
        {lede && <p className="ph-lede">{lede}</p>}
      </div>
      {actions && <div className="ph-actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, actions, children, className = '', pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`card ${pad ? '' : 'card-flush'} ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, icon, tone }: { label: string; value: ReactNode; sub?: ReactNode; icon?: IconName; tone?: 'alert' | 'warn' }) {
  return (
    <div className={`kpi ${tone ? `kpi-${tone}` : ''}`}>
      <span className="kpi-label">
        {icon && <Icon name={icon} size={16} />}
        {label}
      </span>
      <span className="kpi-value">{value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

export function KeyValues({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ status */

/** Warm-only status vocabulary; meaning is always carried by icon + text, never colour alone. */
export type Tone = 'gold' | 'ok' | 'warn' | 'alert' | 'muted';
const TONE_ICON: Record<Tone, IconName | null> = { gold: null, ok: 'check', warn: 'clock', alert: 'alert', muted: null };

export function Pill({ tone = 'muted', children, icon }: { tone?: Tone; children: ReactNode; icon?: IconName | null }) {
  const ic = icon === undefined ? TONE_ICON[tone] : icon;
  return (
    <span className={`pill pill-${tone}`}>
      {ic && <Icon name={ic} size={12} strokeWidth={2} />}
      {children}
    </span>
  );
}

export const statusTone = (s: string): Tone => {
  if (['Settled', 'Approved', 'Within tolerance', 'Reconciled', 'Acknowledged', 'Done', 'Resolved'].includes(s)) return 'ok';
  if (['Exception', 'High', 'On hold', 'Overdue'].includes(s)) return 'alert';
  if (['Pending approval', 'Pending', 'In progress', 'Medium', 'Under review', 'Partial', 'Open'].includes(s)) return 'warn';
  if (['Issued', 'In production', 'Returned'].includes(s)) return 'gold';
  return 'muted';
};

export function DemoNote({ children }: { children: ReactNode }) {
  return (
    <p className="demo-note" role="note">
      <Icon name="flame" size={13} />
      {children}
    </p>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name="search" size={22} />
      <strong>{title}</strong>
      {children && <span>{children}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ tabs */

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { key: T; label: string; count?: number }[]; value: T; onChange: (t: T) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={value === t.key ? 'is-on' : ''} onClick={() => onChange(t.key)}>
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ table */

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sort?: (row: T) => string | number;
  align?: 'right';
  hideSm?: boolean;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  initialSort,
  empty = 'Nothing matches the current filters.',
  caption,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (r: T) => string;
  onRowClick?: (r: T) => void;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
  empty?: string;
  caption?: string;
}) {
  const [sort, setSort] = useState(initialSort);
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key);
    if (!col?.sort || !sort) return rows;
    const get = col.sort;
    return [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return sort.dir === 'asc' ? c : -c;
    });
  }, [rows, columns, sort]);

  return (
    <div className="table-wrap">
      <table className="table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th key={c.key} className={`${c.align === 'right' ? 'num' : ''} ${c.hideSm ? 'hide-sm' : ''}`} aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                  {c.sort ? (
                    <button className="th-sort" onClick={() => setSort({ key: c.key, dir: active && sort!.dir === 'asc' ? 'desc' : 'asc' })}>
                      {c.header}
                      <span aria-hidden="true" className={`th-caret ${active ? 'is-on' : ''}`}>{active && sort!.dir === 'desc' ? '▾' : '▴'}</span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={rowKey(r)}
              className={onRowClick ? 'is-clickable' : ''}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              onKeyDown={onRowClick ? (e) => (e.key === 'Enter' ? onRowClick(r) : undefined) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} className={`${c.align === 'right' ? 'num' : ''} ${c.hideSm ? 'hide-sm' : ''}`}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && <Empty title={empty} />}
    </div>
  );
}

/* ------------------------------------------------------------------ filters */

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="toolbar">{children}</div>;
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="search">
      <Icon name="search" size={16} />
      <span className="sr-only">{placeholder}</span>
      <input type="search" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function SelectFilter({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: (string | { value: string; label: string })[] }) {
  return (
    <label className="select-filter">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => {
          const v = typeof o === 'string' ? o : o.value;
          const l = typeof o === 'string' ? o : o.label;
          return (
            <option key={v} value={v}>
              {l}
            </option>
          );
        })}
      </select>
    </label>
  );
}

/* ------------------------------------------------------------------ buttons */

export function Btn({ children, icon, variant = 'ghost', size = 'md', ...rest }: { children: ReactNode; icon?: IconName; variant?: 'gold' | 'ghost' | 'quiet'; size?: 'sm' | 'md' } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`abtn abtn-${variant} abtn-${size}`} type="button" {...rest}>
      {icon && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
      <span>{children}</span>
    </button>
  );
}

/* ------------------------------------------------------------------ dialog */

export function Dialog({ open, title, onClose, children, footer }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // keep the latest onClose without re-running the open/focus effect on every render
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const first =
      ref.current?.querySelector<HTMLElement>('.dlg-body input:not([disabled]):not([readonly]), .dlg-body select, .dlg-body textarea') ??
      ref.current?.querySelector<HTMLElement>('button');
    first?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeRef.current();
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      prev?.focus();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="dlg-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="dlg" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dlg-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close dialog">
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="dlg-body">{children}</div>
        {footer && <div className="dlg-foot">{footer}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ fields */

export function Field({ label, hint, children, wide }: { label: string; hint?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`field ${wide ? 'field-wide' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function FormGrid({ children }: { children: ReactNode }) {
  return <div className="form-grid">{children}</div>;
}

export function FormMessage({ result }: { result: { ok: boolean; text: string } | null }) {
  if (!result) return null;
  return (
    <p className={`form-msg ${result.ok ? 'is-ok' : 'is-err'}`} role={result.ok ? 'status' : 'alert'}>
      <Icon name={result.ok ? 'check' : 'alert'} size={14} strokeWidth={2} />
      {result.text}
    </p>
  );
}

/* ------------------------------------------------------------------ timeline */

export interface TimelineItem {
  id: string;
  date: string;
  title: ReactNode;
  meta?: ReactNode;
  value?: ReactNode;
  icon?: IconName;
  flag?: boolean;
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  if (!items.length) return <Empty title="No events yet" />;
  return (
    <ol className="tl">
      {items.map((it) => (
        <li key={it.id} className={it.flag ? 'is-flag' : ''}>
          <span className="tl-dot">{it.icon && <Icon name={it.icon} size={13} />}</span>
          <div className="tl-main">
            <strong>{it.title}</strong>
            <small>
              {it.date}
              {it.meta && <> · {it.meta}</>}
            </small>
          </div>
          {it.value && <span className="tl-val">{it.value}</span>}
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ bars */

export function BarList({ items, format }: { items: { label: ReactNode; value: number; key: string }[]; format: (n: number) => string }) {
  const max = Math.max(0.0001, ...items.map((i) => Math.abs(i.value)));
  return (
    <ul className="barlist">
      {items.map((i) => (
        <li key={i.key}>
          <span className="barlist-label">{i.label}</span>
          <span className="barlist-track" aria-hidden="true">
            <span style={{ width: `${(Math.abs(i.value) / max) * 100}%` }} />
          </span>
          <span className="barlist-val">{format(i.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ chart */

/**
 * Two-series line chart (validated warm pair: gold #b8892e / copper #9c4a33 on the card surface),
 * with dash as secondary encoding, legend, direct end labels, crosshair tooltip and a table view.
 */
export function LineChart2({ labels, a, b, unit, caption }: { labels: string[]; a: { name: string; data: number[] }; b: { name: string; data: number[] }; unit: string; caption: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = 240;
  const P = { l: 44, r: 110, t: 14, b: 26 };
  const max = Math.max(1, ...a.data, ...b.data) * 1.12;
  const n = labels.length;
  const x = (i: number) => P.l + (n === 1 ? 0 : (i / (n - 1)) * (W - P.l - P.r));
  const y = (v: number) => P.t + (1 - v / max) * (H - P.t - P.b);
  const path = (d: number[]) => d.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const last = n - 1;
  const series = [
    { ...a, color: '#b8892e', dash: undefined as string | undefined },
    { ...b, color: '#9c4a33', dash: '5 4' },
  ];
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = (e.clientX - r.left) / r.width;
    setHover(Math.max(0, Math.min(last, Math.round(f * last))));
  };
  const step = Math.max(1, Math.ceil(n / 6));
  return (
    <figure className="chart">
      <figcaption className="chart-legend">
        {series.map((s) => (
          <span key={s.name}>
            <svg width="22" height="8" aria-hidden="true">
              <line x1="1" x2="21" y1="4" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
            </svg>
            {s.name}
          </span>
        ))}
      </figcaption>
      <div className="chart-plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={caption}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="chart-grid" />
              <text x={P.l - 8} y={y(t) + 3} textAnchor="end" className="chart-axis">
                {t}
              </text>
            </g>
          ))}
          {labels.map((l, i) =>
            i % step === 0 || i === last ? (
              <text key={l + i} x={x(i)} y={H - 6} textAnchor="middle" className="chart-axis">
                {l}
              </text>
            ) : null,
          )}
          {series.map((s) => (
            <path key={s.name} d={path(s.data)} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {series.map((s, si) => (
            <g key={s.name}>
              <circle cx={x(last)} cy={y(s.data[last])} r={4} fill={s.color} stroke="#14100b" strokeWidth={2} />
              <text x={x(last) + 10} y={y(s.data[last]) + (si === 0 ? -3 : 11)} className="chart-end">
                {s.name} {s.data[last].toFixed(1)}
              </text>
            </g>
          ))}
          {hover !== null && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={y(0)} className="chart-cross" />
              {series.map((s) => (
                <circle key={s.name} cx={x(hover)} cy={y(s.data[hover])} r={4.5} fill={s.color} stroke="#14100b" strokeWidth={2} />
              ))}
            </g>
          )}
          <rect x={P.l} y={P.t} width={W - P.l - P.r} height={H - P.t - P.b} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
        {hover !== null && (
          <div className="chart-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
            <strong>{labels[hover]}</strong>
            {series.map((s) => (
              <span key={s.name}>
                <i style={{ background: s.color }} />
                {s.name}
                <b>
                  {s.data[hover].toFixed(3)} {unit}
                </b>
              </span>
            ))}
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>{a.name}</th>
            <th>{b.name}</th>
          </tr>
        </thead>
        <tbody>
          {labels.map((l, i) => (
            <tr key={l + i}>
              <td>{l}</td>
              <td>{a.data[i]}</td>
              <td>{b.data[i]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/* ------------------------------------------------------------------ csv */

/** Real client-side export of what's on screen (no server involved). */
export function downloadCsv(filename: string, header: string[], rows: (string | number)[][]) {
  const esc = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [header, ...rows].map((r) => r.map(esc).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
