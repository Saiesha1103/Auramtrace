import { useLayoutEffect, useRef } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { SplitText } from '../components/SplitText';
import { MovementChart } from './MovementChart';
import { gsap, prefersReducedMotion } from '../lib/motion';
import { useReveal } from '../lib/useReveal';
import './ProductPreview.css';

const KPIS: { label: string; value: number; decimals: number; unit?: string; sub: string; icon: IconName }[] = [
  { label: 'Active jobs', value: 42, decimals: 0, sub: '11 at subcontractors', icon: 'manufacture' },
  { label: 'Gold issued · MTD', value: 1284.65, decimals: 3, unit: 'g', sub: 'fine-gold equivalent', icon: 'issue' },
  { label: 'Pending returns', value: 186.22, decimals: 3, unit: 'g', sub: 'across 9 jobs', icon: 'return' },
  { label: 'Reconciliation exceptions', value: 3, decimals: 0, sub: '1 high priority', icon: 'alert' },
];

const EXCEPTIONS = [
  { id: 'EX-2041', job: 'J-1182 · Karigar 07', delta: '−0.564 g', level: 'high', label: 'High' },
  { id: 'EX-2038', job: 'J-1175 · Subcontractor S-03', delta: '−0.212 g', level: 'medium', label: 'Review' },
  { id: 'EX-2033', job: 'J-1160 · Karigar 02', delta: '−0.098 g', level: 'low', label: 'Low' },
];

const HISTORY = [
  { t: '10:42', ev: 'Return', job: 'J-1182', route: 'Karigar 07 → Vault', gross: '41.208', fine: '30.226', status: 'Pending', tone: 'warn' },
  { t: '10:15', ev: 'Transfer', job: 'J-1190', route: 'Vault → Karigar 03', gross: '25.000', fine: '25.000', status: 'Signed', tone: 'ok' },
  { t: '09:58', ev: 'Issue', job: 'J-1191', route: 'Vault → Head karigar', gross: '60.000', fine: '60.000', status: 'Signed', tone: 'ok' },
  { t: '09:31', ev: 'Return', job: 'J-1175', route: 'S-03 → Karigar 05', gross: '18.742', fine: '13.743', status: 'Exception', tone: 'alert' },
  { t: '09:02', ev: 'Manufacture', job: 'J-1168', route: 'Casting · S-01', gross: '—', fine: '—', status: 'In progress', tone: 'muted' },
];

const NAV: IconName[] = ['reconcile', 'transfer', 'layers', 'search', 'doc', 'user'];

export function ProductPreview() {
  const root = useRef<HTMLElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  useReveal(root);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const counters = el.querySelectorAll<HTMLElement>('[data-count]');
    const fmt = (v: number, d: number) =>
      v.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });

    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      // the console tilts up out of the dark, like a product reveal
      gsap.fromTo(
        frame.current,
        { rotateX: 22, y: 80, scale: 0.9, autoAlpha: 0.2 },
        {
          rotateX: 0,
          y: 0,
          scale: 1,
          autoAlpha: 1,
          ease: 'none',
          scrollTrigger: { trigger: frame.current, start: 'top 95%', end: 'top 25%', scrub: 0.8 },
        },
      );

      counters.forEach((c) => {
        const target = Number(c.dataset.count);
        const d = Number(c.dataset.decimals);
        const s = { v: 0 };
        c.textContent = fmt(0, d);
        gsap.to(s, {
          v: target,
          duration: 2.2,
          ease: 'expo.out',
          onUpdate: () => (c.textContent = fmt(s.v, d)),
          scrollTrigger: { trigger: frame.current, start: 'top 60%', once: true },
        });
      });

      gsap.from('.mchart-line', {
        strokeDashoffset: 1,
        strokeDasharray: 1,
        duration: 2.4,
        ease: 'power2.inOut',
        stagger: 0.25,
        scrollTrigger: { trigger: '.mchart', start: 'top 75%', once: true },
        onComplete() {
          gsap.set('.mchart-line', { clearProps: 'strokeDasharray,strokeDashoffset' });
        },
      });
      gsap.from('.dash-row', {
        autoAlpha: 0,
        x: -12,
        stagger: 0.08,
        duration: 0.9,
        scrollTrigger: { trigger: '.dash-table', start: 'top 85%', once: true },
      });
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={root} id="dashboard" className="section preview" aria-labelledby="preview-title">
      <div className="container">
        <div className="section-head center">
          <span className="eyebrow" data-reveal>
            The manufacturer console
          </span>
          <SplitText id="preview-title" segments={[{ text: 'Your Gold Position,' }, { text: 'At a Glance.', em: true }]} breakAfter={[0]} />
          <p className="lede" data-reveal>
            One live ledger for every job, karigar and vault — what is out, what is due back, and what needs a closer
            look.
          </p>
        </div>

        <div className="preview-stage">
          <div className="preview-halo" aria-hidden="true" />
          <div ref={frame} className="dash" role="group" aria-label="AURUMTRACE dashboard preview with illustrative demo data">
            <div className="dash-chrome">
              <span className="dash-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <span className="dash-title">AURUMTRACE · Manufacturer console</span>
              <span className="demo-tag">
                <Icon name="flame" size={12} /> Demo workspace — illustrative data
              </span>
            </div>

            <div className="dash-body">
              <aside className="dash-nav" aria-hidden="true">
                {NAV.map((n, i) => (
                  <span key={n} className={i === 0 ? 'is-on' : ''}>
                    <Icon name={n} size={20} />
                  </span>
                ))}
              </aside>

              <div className="dash-main">
                <div className="dash-kpis">
                  {KPIS.map((k) => (
                    <div key={k.label} className={`dash-kpi ${k.icon === 'alert' ? 'is-alert' : ''}`}>
                      <span className="dash-kpi-label">
                        <Icon name={k.icon} size={16} />
                        {k.label}
                      </span>
                      <span className="dash-kpi-value">
                        <span data-count={k.value} data-decimals={k.decimals}>
                          {k.value.toLocaleString('en-IN', { minimumFractionDigits: k.decimals })}
                        </span>
                        {k.unit && <small>{k.unit}</small>}
                      </span>
                      <span className="dash-kpi-sub">{k.sub}</span>
                    </div>
                  ))}
                </div>

                <div className="dash-grid">
                  <div className="dash-card dash-chart">
                    <MovementChart />
                  </div>

                  <div className="dash-card dash-exc">
                    <span className="dash-card-title">Reconciliation exceptions</span>
                    <ul>
                      {EXCEPTIONS.map((e) => (
                        <li key={e.id}>
                          <span className={`sev sev-${e.level}`}>
                            <Icon name={e.level === 'low' ? 'clock' : 'alert'} size={13} strokeWidth={1.8} />
                            {e.label}
                          </span>
                          <span className="exc-main">
                            <b>{e.id}</b>
                            <small>{e.job}</small>
                          </span>
                          <span className="exc-delta">{e.delta}</span>
                        </li>
                      ))}
                    </ul>
                    <a className="exc-link" href="#investigation">
                      Investigate EX-2041 <Icon name="arrow" size={14} />
                    </a>
                  </div>
                </div>

                <div className="dash-card dash-table">
                  <span className="dash-card-title">Gold movement history</span>
                  <div className="dash-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Event</th>
                          <th>Job</th>
                          <th>Custody</th>
                          <th className="num">Gross (g)</th>
                          <th className="num">Fine (g)</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {HISTORY.map((h) => (
                          <tr key={h.t} className="dash-row">
                            <td className="mono">{h.t}</td>
                            <td>{h.ev}</td>
                            <td className="mono">{h.job}</td>
                            <td>{h.route}</td>
                            <td className="num mono">{h.gross}</td>
                            <td className="num mono">{h.fine}</td>
                            <td>
                              <span className={`pill pill-${h.tone}`}>{h.status}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
