import { Component, lazy, Suspense, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '../components/Button';
import { SplitText } from '../components/SplitText';
import { gsap, prefersReducedMotion } from '../lib/motion';
import { hasWebGL } from '../lib/webgl';
import { useInView } from '../lib/useInView';
import { useReducedMotion } from '../lib/useReducedMotion';
import { useReveal } from '../lib/useReveal';
import { seaState } from '../three/seaState';
import './FinalCTA.css';

const MoltenSea = lazy(() => import('../three/MoltenSea'));

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function FinalCTA() {
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const near = useInView(root, '400px'); // mount the canvas just before it scrolls in
  const inView = useInView(root, '0px');
  const [webgl] = useState(() => hasWebGL());
  const [mounted, setMounted] = useState(false);
  useReveal(root);

  if (near && !mounted) setMounted(true);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      seaState.reveal = 1;
      el.style.setProperty('--sea', '1');
      return;
    }
    const ctx = gsap.context(() => {
      gsap.to(seaState, {
        reveal: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: el,
          start: 'top 85%',
          end: 'center 55%',
          scrub: 1,
          onUpdate: (st) => el.style.setProperty('--sea', st.progress.toFixed(3)),
        },
      });
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={root} id="cta" className="cta" aria-labelledby="cta-title">
      <div className="cta-bg" aria-hidden="true">
        <div className="cta-fallback" />
        {webgl && mounted && (
          <Boundary>
            <Suspense fallback={null}>
              <MoltenSea active={inView} reduced={reduced} />
            </Suspense>
          </Boundary>
        )}
        <div className="cta-vignette" />
      </div>

      <div className="container cta-inner">
        <span className="eyebrow" data-reveal>
          From issue to settlement
        </span>
        <SplitText
          id="cta-title"
          className="display cta-title"
          segments={[{ text: 'Bring Every Gram' }, { text: 'Into Focus.', em: true }]}
          breakAfter={[0]}
        />
        <p className="lede" data-reveal>
          See how AURUMTRACE gives your floor, your karigars and your auditors one trusted record of every gram.
        </p>
        <div className="cta-actions" data-reveal>
          <Button href="#top" size="lg" icon="arrow">
            Explore AURUMTRACE
          </Button>
        </div>
      </div>

      <footer className="footer">
        <span className="footer-brand">AURUMTRACE</span>
        <span>Precious-metal custody &amp; manufacturing intelligence.</span>
        <span>All product figures shown on this page are illustrative demo data.</span>
      </footer>
    </section>
  );
}
