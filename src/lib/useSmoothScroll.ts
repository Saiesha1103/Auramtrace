import { useEffect } from 'react';
import Lenis from 'lenis';
import { gsap, ScrollTrigger } from './motion';

let lenis: Lenis | null = null;

/** Smoothly scroll to an in-page anchor, honouring Lenis when active. */
export function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  if (lenis) lenis.scrollTo(el, { offset: -20, duration: 1.6 });
  else el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Inertial scrolling synced to GSAP's ticker so ScrollTrigger stays frame-perfect. */
export function useSmoothScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    lenis = new Lenis({ lerp: 0.09, smoothWheel: true, wheelMultiplier: 0.95, anchors: true });
    lenis.on('scroll', ScrollTrigger.update);
    const tick = (time: number) => lenis?.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis?.destroy();
      lenis = null;
    };
  }, [enabled]);
}
