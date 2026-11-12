import { useMemo, useState } from 'react';

/**
 * Two-series line chart: gold issued vs. returned per day (illustrative data).
 * Palette validated with the dataviz checker against the dark panel surface.
 */
const ISSUED = [82, 96, 74, 110, 128, 91, 64, 102, 118, 135, 97, 88, 124, 140];
const RETURNED = [70, 88, 79, 95, 115, 98, 60, 90, 112, 121, 104, 80, 110, 126];
const DAYS = ISSUED.map((_, i) => {
  const d = new Date(2026, 9, 30 + i);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
});

const SERIES = [
  { key: 'issued', label: 'Issued', color: '#b5802a', data: ISSUED },
  { key: 'returned', label: 'Returned', color: '#3d8bd9', data: RETURNED },
] as const;

const W = 640;
const H = 220;
const PAD = { l: 40, r: 104, t: 14, b: 26 };
const MAX = 160;

const x = (i: number) => PAD.l + (i / (ISSUED.length - 1)) * (W - PAD.l - PAD.r);
const y = (v: number) => PAD.t + (1 - v / MAX) * (H - PAD.t - PAD.b);

function linePath(data: readonly number[]) {
  return data.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
}

export function MovementChart() {
  const [hover, setHover] = useState<number | null>(null);
  const paths = useMemo(() => SERIES.map((s) => linePath(s.data)), []);
  const area = `${paths[0]} L${x(ISSUED.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const last = ISSUED.length - 1;

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * (W - PAD.l - PAD.r);
    const i = Math.round((px / (W - PAD.l - PAD.r)) * last);
    setHover(Math.max(0, Math.min(last, i)));
  };

  return (
    <figure className="mchart">
      <figcaption className="mchart-head">
        <span className="dash-card-title">Gold movement · last 14 days (g)</span>
        <span className="mchart-legend" aria-hidden="true">
          {SERIES.map((s) => (
            <span key={s.key}>
              <i style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </span>
      </figcaption>
      <div className="mchart-plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Line chart of grams issued versus returned per day, illustrative data">
          <defs>
            <linearGradient id="mchart-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#b5802a" stopOpacity="0.28" />
              <stop offset="1" stopColor="#b5802a" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 40, 80, 120, 160].map((v) => (
            <g key={v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="mchart-grid" />
              <text x={PAD.l - 8} y={y(v) + 3} className="mchart-axis" textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          {DAYS.map((d, i) =>
            i % 3 === 1 ? (
              <text key={d} x={x(i)} y={H - 6} className="mchart-axis" textAnchor="middle">
                {d}
              </text>
            ) : null,
          )}
          <path d={area} fill="url(#mchart-area)" className="mchart-area" />
          {SERIES.map((s, si) => (
            <path key={s.key} d={paths[si]} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className="mchart-line" pathLength={1} />
          ))}
          {/* direct end labels */}
          {SERIES.map((s) => (
            <g key={s.key}>
              <circle cx={x(last)} cy={y(s.data[last])} r={4} fill={s.color} stroke="#120e09" strokeWidth={2} />
              <text x={x(last) + 10} y={y(s.data[last]) + (s.key === 'issued' ? -2 : 10)} className="mchart-end">
                {s.label} {s.data[last]}
              </text>
            </g>
          ))}
          {hover !== null && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={y(0)} className="mchart-cross" />
              {SERIES.map((s) => (
                <circle key={s.key} cx={x(hover)} cy={y(s.data[hover])} r={4.5} fill={s.color} stroke="#120e09" strokeWidth={2} />
              ))}
            </g>
          )}
          <rect
            x={PAD.l}
            y={PAD.t}
            width={W - PAD.l - PAD.r}
            height={H - PAD.t - PAD.b}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
        {hover !== null && (
          <div className="mchart-tip" style={{ left: `${(x(hover) / W) * 100}%` }} role="status">
            <strong>{DAYS[hover]}</strong>
            {SERIES.map((s) => (
              <span key={s.key}>
                <i style={{ background: s.color }} />
                {s.label}
                <b>{s.data[hover].toFixed(3)} g</b>
              </span>
            ))}
            <span className="mchart-tip-net">
              Net in custody <b>{(ISSUED[hover] - RETURNED[hover]).toFixed(3)} g</b>
            </span>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>Gold issued and returned per day (grams, illustrative)</caption>
        <thead>
          <tr>
            <th>Day</th>
            <th>Issued</th>
            <th>Returned</th>
          </tr>
        </thead>
        <tbody>
          {DAYS.map((d, i) => (
            <tr key={d}>
              <td>{d}</td>
              <td>{ISSUED[i]}</td>
              <td>{RETURNED[i]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
