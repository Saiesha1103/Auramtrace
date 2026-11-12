import { Component, lazy, Suspense, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { HeroFallback } from './HeroFallback';
import { NodeLabels } from './NodeLabels';
import { gsap, prefersReducedMotion } from '../lib/motion';
import { hasWebGL, isLiteDevice } from '../lib/webgl';
import { useInView } from '../lib/useInView';
import { useReducedMotion } from '../lib/useReducedMotion';
import { sceneClock } from '../three/clock';
import { labelSafe } from '../three/nodes';
import './Hero.css';

// three.js + the scene are split into their own chunk and fetched after first paint
const GoldScene = lazy(() => import('../three/GoldScene'));

/** If WebGL context creation or a shader fails, keep the poster instead of a blank hero. */
class SceneBoundary extends Component<{ children: ReactNode; onError: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const HEADLINE = [
  ['Intelligent', 'Gold'],
  ['Across', 'Every', 'Stage.'],
];

export function Hero() {
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const inView = useInView(root, '0px');
  const [webgl] = useState(() => hasWebGL());
  const [lite] = useState(() => isLiteDevice());
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const showScene = webgl && !failed;

  // keep floating node labels clear of the copy column
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => {
      labelSafe.copyEls = Array.from(el.querySelectorAll<HTMLElement>('.hero-pill, .hero-title .split-line, .hero-lede, .hero-ctas > *, .hero-meta'));
      labelSafe.minY = (document.querySelector('.nav')?.getBoundingClientRect().height ?? 0) + 8;
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    document.fonts?.ready.then(measure);
    return () => ro.disconnect();
  }, []);

  // intro choreography + scroll-out
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const ctx = gsap.context(() => {
      if (!prefersReducedMotion()) {
        const tl = gsap.timeline({ defaults: { ease: 'expo.out' }, delay: 0.15 });
        tl.from('.hero-pill', { autoAlpha: 0, y: 16, duration: 1 })
          .from('.hero-title .split-word', { yPercent: 118, rotate: 3, duration: 1.5, stagger: 0.08 }, '-=0.7')
          .from('.hero-lede', { autoAlpha: 0, y: 22, duration: 1.2 }, '-=1.05')
          .from('.hero-ctas > *', { autoAlpha: 0, y: 18, duration: 1.1, stagger: 0.1 }, '-=0.95')
          .from('.hero-meta', { autoAlpha: 0, duration: 1.2 }, '-=0.8');
      }

      gsap.to('.hero-content', {
        yPercent: -14,
        autoAlpha: 0.0,
        ease: 'none',
        scrollTrigger: { trigger: el, start: 'top top', end: 'bottom top', scrub: true },
      });
      gsap.to('.hero-stage', {
        yPercent: 18,
        ease: 'none',
        scrollTrigger: {
          trigger: el,
          start: 'top top',
          end: 'bottom top',
          scrub: true,
          onUpdate: (st) => {
            sceneClock.scroll = st.progress;
          },
        },
      });
    }, el);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={root} id="top" className="hero" aria-labelledby="hero-title">
      <div className="hero-stage" aria-hidden="true">
        <HeroFallback dimmed={showScene && ready} animate={!reduced} />
        {showScene && (
          <div className={`hero-canvas ${ready ? 'is-ready' : ''}`}>
            <SceneBoundary onError={() => setFailed(true)}>
              <Suspense fallback={null}>
                <GoldScene active={inView} reduced={reduced} lite={lite} onReady={() => setReady(true)} />
              </Suspense>
            </SceneBoundary>
            <NodeLabels visible={ready} />
          </div>
        )}
        <div className="hero-scrim" />
      </div>

      <div className="hero-content container">
        <div className="hero-copy">
          <p className="hero-pill">
            <Icon name="sparkle" size={14} gold />
            Precious-metal intelligence platform
          </p>

          <h1 id="hero-title" className="display hero-title" aria-label="Intelligent Gold Across Every Stage.">
            {HEADLINE.map((line, li) => (
              <span key={li} className="hero-line">
                {line.map((w, wi) => (
                  <span key={wi} className="split-line" aria-hidden="true">
                    {li === 1 && wi > 0 ? <em className="split-word">{w}</em> : <span className="split-word">{w}</span>}
                  </span>
                ))}
              </span>
            ))}
          </h1>

          <p className="lede hero-lede">
            Track, reconcile and secure every gram — from the moment gold is issued to the final settlement. End-to-end
            custody traceability, fine-gold reconciliation and AI-powered investigation for jewellery manufacturers.
          </p>

          <div className="hero-ctas">
            <Button href="#platform" size="lg" icon="arrow">
              Explore Platform
            </Button>
            <Button href="#journey" size="lg" variant="ghost" iconLeft="play">
              See How It Works
            </Button>
          </div>

          <p className="hero-meta">
            <span>Manufacturer</span>
            <i aria-hidden="true" />
            <span>Head karigar</span>
            <i aria-hidden="true" />
            <span>Subcontractor</span>
          </p>
        </div>
      </div>

      <div className="hero-scroll" aria-hidden="true">
        <span />
      </div>
    </section>
  );
}
