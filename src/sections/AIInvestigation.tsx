import { useLayoutEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { SplitText } from '../components/SplitText';
import { gsap, prefersReducedMotion } from '../lib/motion';
import { useReveal } from '../lib/useReveal';
import './AIInvestigation.css';

const STEPS: { icon: IconName; title: string; body: string; status: string }[] = [
  { icon: 'alert', title: 'Discrepancy identified', body: 'Reconciliation flags a variance beyond the process-loss allowance.', status: 'Detected' },
  { icon: 'search', title: 'Material events traced', body: 'Every custody event on the job is pulled into one timeline.', status: 'Tracing' },
  { icon: 'link', title: 'Evidence linked', body: 'Weighing slips, assays and calibration logs attach to the events they support.', status: 'Evidence linked' },
  { icon: 'sparkle', title: 'Explanation generated', body: 'A cited, quantified explanation — never a black-box verdict.', status: 'Explained' },
  { icon: 'user', title: 'Manager review', body: 'A person approves, challenges or escalates. Every decision is logged.', status: 'Approved' },
];

// Illustrative case — all figures are internally consistent demo data.
const EVENTS = [
  { d: '02 Nov · 09:58', t: 'Issue', v: '30.000 g fine', note: 'Vault → Head karigar' },
  { d: '02 Nov · 14:20', t: 'Transfer', v: '30.000 g', note: 'Head karigar → Karigar 07' },
  { d: '05 Nov · 11:05', t: 'Casting', v: 'loss 0.180 g', note: 'Subcontractor S-01' },
  { d: '08 Nov · 16:40', t: 'Scrap return', v: '1.040 g gross', note: 'Declared 22K · assayed 18K', flag: true },
  { d: '12 Nov · 10:42', t: 'Finished return', v: '28.656 g fine', note: '31.284 g @ 91.6%' },
];

const EVIDENCE = [
  { id: 'E1', icon: 'doc' as IconName, label: 'Assay report AR-3307', note: 'Scrap lot at 75.0% purity' },
  { id: 'E2', icon: 'scan' as IconName, label: 'Weighing slip WS-8821', note: 'Photo + scale ID 4' },
  { id: 'E3', icon: 'clock' as IconName, label: 'Scale 4 calibration log', note: 'Drift +0.03 g since 01 Nov' },
];

export function AIInvestigation() {
  const root = useRef<HTMLElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  useReveal(root);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      setStep(STEPS.length - 1);
      return;
    }
    const mm = gsap.matchMedia();
    mm.add('(min-width: 1025px) and (min-height: 820px)', () => {
      const st = gsap.timeline({
        scrollTrigger: {
          trigger: pin.current,
          start: 'top top',
          end: '+=320%',
          pin: true,
          scrub: true,
          anticipatePin: 1,
          onUpdate: (self) => {
            const s = Math.min(STEPS.length - 1, Math.floor(self.progress * STEPS.length * 0.999 + 0.15));
            setStep((p) => (p === s ? p : s));
            el.style.setProperty('--inv-progress', self.progress.toFixed(4));
          },
        },
      });
      return () => st.kill();
    });
    mm.add('(max-width: 1024px), (max-height: 819px)', () => {
      setStep(STEPS.length - 1);
    });
    return () => mm.revert();
  }, []);

  const on = (i: number) => (step >= i ? 'is-on' : '');

  return (
    <section ref={root} id="investigation" className="section inv" aria-labelledby="inv-title">
      <div ref={pin} className="inv-pin">
        <div className="container inv-grid">
          <div className="inv-copy">
            <span className="eyebrow" data-reveal>
              AI investigation
            </span>
            <SplitText
              id="inv-title"
              segments={[{ text: "Don't Just Find Variances." }, { text: 'Understand Them.', em: true }]}
              breakAfter={[0]}
            />
            <p className="lede" data-reveal>
              When gold goes missing on paper, AURUMTRACE assembles the case: the events, the evidence and a cited
              explanation your team can verify.
            </p>

            <ol className="inv-steps" data-reveal>
              <span className="inv-steps-line" aria-hidden="true">
                <span />
              </span>
              {STEPS.map((s, i) => (
                <li key={s.title} className={`${on(i)} ${step === i ? 'is-current' : ''}`}>
                  <span className="inv-step-icon">
                    <Icon name={s.icon} size={18} strokeWidth={1.6} />
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>{s.body}</small>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div className="inv-console" data-reveal aria-live="polite">
            <header className="inv-head">
              <div>
                <span className="inv-case">Case EX-2041</span>
                <span className="inv-sub">Job J-1182 · Karigar 07 · 22K bangles</span>
              </div>
              <span className={`inv-status s-${step}`}>
                <i />
                {STEPS[step].status}
              </span>
            </header>

            {/* 1 — detect */}
            <div className={`inv-block inv-recon ${on(0)}`}>
              <div className="inv-metric">
                <small>Issued (fine)</small>
                <b>30.000 g</b>
              </div>
              <div className="inv-metric">
                <small>Returned (fine)</small>
                <b>29.436 g</b>
              </div>
              <div className="inv-metric">
                <small>Allowance 1.20%</small>
                <b>0.360 g</b>
              </div>
              <div className="inv-metric is-alert">
                <small>Unexplained</small>
                <b>0.204 g</b>
              </div>
              <div className="inv-bar" aria-hidden="true">
                <span className="inv-bar-ok" />
                <span className="inv-bar-bad" />
              </div>
            </div>

            <div className="inv-cols">
              {/* 2 — trace */}
              <div className={`inv-block inv-events ${on(1)}`}>
                <span className="inv-label">Custody timeline</span>
                <ol>
                  {EVENTS.map((e, i) => (
                    <li key={e.d} className={`${e.flag && step >= 2 ? 'is-flag' : ''}`} style={{ transitionDelay: `${i * 70}ms` }}>
                      <span className="ev-dot" />
                      <span className="ev-main">
                        <b>{e.t}</b>
                        <small>
                          {e.d} · {e.note}
                        </small>
                      </span>
                      <span className="ev-val">{e.v}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* 3 — evidence */}
              <div className={`inv-block inv-evidence ${on(2)}`}>
                <span className="inv-label">Linked evidence</span>
                <ul>
                  {EVIDENCE.map((e, i) => (
                    <li key={e.id} style={{ transitionDelay: `${i * 90}ms` }}>
                      <span className="evd-id">{e.id}</span>
                      <Icon name={e.icon} size={16} />
                      <span>
                        <b>{e.label}</b>
                        <small>{e.note}</small>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* 4 — explanation */}
            <div className={`inv-block inv-explain ${on(3)}`}>
              <span className="inv-label">
                <Icon name="sparkle" size={14} gold /> Explanation · confidence 0.86
              </span>
              <p>
                The 0.204 g gap is best explained by the <mark>08 Nov scrap return</mark>: declared 22K but assayed at 18K{' '}
                <cite>E1</cite>, which overstates fine content by <b>0.173 g</b>. The remaining <b>0.031 g</b> sits within
                Scale 4’s logged calibration drift <cite>E2</cite> <cite>E3</cite>.
              </p>
              <div className="inv-conf" aria-hidden="true">
                <span style={{ width: '86%' }} />
              </div>
            </div>

            {/* 5 — review */}
            <div className={`inv-block inv-review ${on(4)}`}>
              <span className="inv-reviewer">
                <span className="inv-avatar">
                  <Icon name="user" size={16} />
                </span>
                <span>
                  <b>Production manager</b>
                  <small>Reviewed findings · 12 Nov 15:08</small>
                </span>
              </span>
              <span className="inv-actions">
                <span className="inv-btn is-primary">
                  <Icon name="check" size={14} strokeWidth={2} /> Approved
                </span>
                <span className="inv-btn">Request re-assay</span>
              </span>
            </div>

            <footer className="inv-foot">
              <span className="demo-tag">Illustrative case · demo data</span>
              <span className="inv-audit">Audit log #A-55102</span>
            </footer>
          </div>
        </div>
      </div>
    </section>
  );
}
