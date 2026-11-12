import { useLayoutEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { SplitText } from '../components/SplitText';
import { gsap, prefersReducedMotion } from '../lib/motion';
import { useReveal } from '../lib/useReveal';
import './GoldJourney.css';

type Lane = 0 | 1 | 2;
const LANES = ['Manufacturer', 'Head karigar', 'Subcontractor'];

const STAGES: { icon: IconName; title: string; lane: Lane; body: string; stat: string }[] = [
  {
    icon: 'issue',
    title: 'Issue',
    lane: 0,
    body: 'Fine gold is weighed, assayed and issued against a job — the first custody record.',
    stat: '100.000 g · 24K',
  },
  {
    icon: 'transfer',
    title: 'Transfer',
    lane: 1,
    body: 'Custody moves to the head karigar. Every hand-off is signed, weighed and time-stamped.',
    stat: '30.000 g → Karigar 07',
  },
  {
    icon: 'manufacture',
    title: 'Manufacture',
    lane: 2,
    body: 'Casting, filing and setting at the subcontractor, with process-loss allowances per operation.',
    stat: 'Loss allowance 1.20%',
  },
  {
    icon: 'return',
    title: 'Return',
    lane: 1,
    body: 'Finished pieces, scrap and dust come back and are converted to fine-gold equivalent.',
    stat: '99.436 g fine',
  },
  {
    icon: 'reconcile',
    title: 'Reconcile',
    lane: 0,
    body: 'Issued vs. returned is settled automatically. Anything outside tolerance becomes an exception.',
    stat: 'Variance 0.564 g',
  },
];

// SVG track geometry (viewBox 1000 x 300, one lane = 100 units)
const X = (i: number) => 100 + i * 200;
const Y = (lane: number) => 50 + lane * 100;
const TRACK = STAGES.reduce((d, s, i) => {
  if (i === 0) return `M${X(0)},${Y(s.lane)}`;
  const px = X(i - 1);
  const py = Y(STAGES[i - 1].lane);
  const mx = (px + X(i)) / 2;
  return `${d} C${mx},${py} ${mx},${Y(s.lane)} ${X(i)},${Y(s.lane)}`;
}, '');

export function GoldJourney() {
  const root = useRef<HTMLElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const progressPath = useRef<SVGPathElement>(null);
  const bead = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(-1);
  useReveal(root);

  useLayoutEffect(() => {
    const el = root.current;
    const path = progressPath.current;
    if (!el || !path) return;

    if (prefersReducedMotion()) {
      setActive(STAGES.length - 1);
      return;
    }

    const len = path.getTotalLength();
    // path length at which each stage node is reached
    const stops = STAGES.map((_, i) => {
      if (i === 0) return 0;
      let lo = 0, hi = len;
      for (let k = 0; k < 24; k++) {
        const mid = (lo + hi) / 2;
        if (path.getPointAtLength(mid).x < X(i)) lo = mid;
        else hi = mid;
      }
      return hi / len;
    });

    const update = (p: number) => {
      const at = Math.max(0.0001, p) * len;
      path.style.strokeDashoffset = String(len - at);
      const pt = path.getPointAtLength(at);
      if (bead.current) {
        bead.current.style.left = `${pt.x / 10}%`;
        bead.current.style.top = `${pt.y / 3}%`;
      }
      let idx = -1;
      stops.forEach((s, i) => {
        if (p >= s - 0.002) idx = i;
      });
      setActive((prev) => (prev === idx ? prev : idx));
    };

    path.style.strokeDasharray = String(len);
    update(0);

    const mm = gsap.matchMedia();
    const ctx = gsap.context(() => {
      // tall screens: pin the board while the gold flows through it
      mm.add('(min-width: 901px) and (min-height: 720px)', () => {
        const state = { p: 0 };
        gsap.to(state, {
          p: 1,
          ease: 'none',
          onUpdate: () => update(state.p),
          scrollTrigger: {
            trigger: pin.current,
            start: 'center center',
            end: '+=140%',
            pin: true,
            scrub: 0.8,
            anticipatePin: 1,
          },
        });
      });
      // short screens: same flow, scrubbed as the board passes, no pin (board may exceed the viewport)
      mm.add('(min-width: 901px) and (max-height: 719px)', () => {
        const state = { p: 0 };
        gsap.to(state, {
          p: 1,
          ease: 'none',
          onUpdate: () => update(state.p),
          scrollTrigger: { trigger: pin.current, start: 'top 70%', end: 'bottom 45%', scrub: 0.8 },
        });
      });
      mm.add('(max-width: 900px)', () => {
        gsap.fromTo(
          '.jm-progress',
          { scaleY: 0 },
          {
            scaleY: 1,
            ease: 'none',
            scrollTrigger: { trigger: '.jm-list', start: 'top 70%', end: 'bottom 60%', scrub: 0.6 },
          },
        );
        gsap.utils.toArray<HTMLElement>('.jm-item').forEach((item) => {
          gsap.to(item, {
            scrollTrigger: { trigger: item, start: 'top 68%', toggleClass: 'is-active', once: true },
          });
        });
      });
    }, el);

    return () => {
      ctx.revert();
      mm.revert();
    };
  }, []);

  return (
    <section ref={root} id="journey" className="section journey" aria-labelledby="journey-title">
      <div className="journey-glow" aria-hidden="true" />
      <div className="container">
        <div className="section-head">
          <span className="eyebrow" data-reveal>
            Custody, gram by gram
          </span>
          <SplitText id="journey-title" segments={[{ text: 'Every Gram Has a' }, { text: 'Journey.', em: true }]} />
          <p className="lede" data-reveal>
            Gold changes hands many times before it becomes jewellery. AURUMTRACE follows it across every custody level —
            manufacturer, head karigar and subcontractor — so nothing goes unaccounted for.
          </p>
        </div>

        {/* desktop: pinned, scroll-driven swimlane */}
        <div ref={pin} className="journey-board">
          <ol className="journey-stages">
            {STAGES.map((s, i) => (
              <li key={s.title} className={`jstage ${i <= active ? 'is-active' : ''} ${i === active ? 'is-current' : ''}`}>
                <span className="jstage-step">0{i + 1}</span>
                <span className="jstage-icon">
                  <Icon name={s.icon} size={30} gold strokeWidth={1.3} />
                </span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <span className="jstage-stat">{s.stat}</span>
              </li>
            ))}
          </ol>

          <div className="journey-lanes" aria-hidden="true">
            <div className="lane-labels">
              {LANES.map((l) => (
                <span key={l}>{l}</span>
              ))}
            </div>
            <div className="lane-track">
              {LANES.map((l) => (
                <div key={l} className="lane-row" />
              ))}
              <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="lane-svg">
                <defs>
                  <linearGradient id="jg" x1="0" x2="1">
                    <stop offset="0" stopColor="#b47628" />
                    <stop offset="0.5" stopColor="#fbeec6" />
                    <stop offset="1" stopColor="#e2b35c" />
                  </linearGradient>
                </defs>
                <path d={TRACK} className="lane-base" vectorEffect="non-scaling-stroke" />
                <path d={TRACK} className="lane-progress" ref={progressPath} vectorEffect="non-scaling-stroke" />
              </svg>
              {STAGES.map((s, i) => (
                <span
                  key={s.title}
                  className={`lane-node ${i <= active ? 'is-active' : ''}`}
                  style={{ left: `${X(i) / 10}%`, top: `${Y(s.lane) / 3}%` }}
                />
              ))}
              <div ref={bead} className="lane-bead" />
            </div>
          </div>
        </div>

        {/* mobile: vertical timeline */}
        <ol className="jm-list">
          <span className="jm-line" aria-hidden="true">
            <span className="jm-progress" />
          </span>
          {STAGES.map((s, i) => (
            <li key={s.title} className="jm-item">
              <span className="jm-dot" aria-hidden="true" />
              <div className="jm-card">
                <div className="jm-head">
                  <Icon name={s.icon} size={26} gold strokeWidth={1.4} />
                  <h3>
                    <span>0{i + 1}</span> {s.title}
                  </h3>
                </div>
                <p>{s.body}</p>
                <div className="jm-meta">
                  <span className="jm-lane">{LANES[s.lane]}</span>
                  <span className="jstage-stat">{s.stat}</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <p className="journey-note">
          <span className="demo-tag">Illustrative figures</span>
        </p>
      </div>
    </section>
  );
}
