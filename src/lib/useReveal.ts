import { useLayoutEffect, type RefObject } from 'react';
import { gsap, ScrollTrigger, prefersReducedMotion } from './motion';

/**
 * Scroll-reveals descendants of `scope`:
 *  - `.split-word` inside `[data-split]` rise out of a mask, word by word
 *  - `[data-reveal]` fade/rise in, staggered in batches
 */
export function useReveal(scope: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const root = scope.current;
    if (!root || prefersReducedMotion()) return;
    const ctx = gsap.context(() => {
      root.querySelectorAll<HTMLElement>('[data-split]').forEach((el) => {
        gsap.from(el.querySelectorAll('.split-word'), {
          yPercent: 115,
          rotate: 2,
          duration: 1.25,
          ease: 'expo.out',
          stagger: 0.06,
          scrollTrigger: { trigger: el, start: 'top 86%', once: true },
        });
      });
      const items = root.querySelectorAll<HTMLElement>('[data-reveal]');
      if (items.length) {
        gsap.set(items, { autoAlpha: 0, y: 28 });
        ScrollTrigger.batch(items, {
          start: 'top 88%',
          once: true,
          onEnter: (batch) =>
            gsap.to(batch, { autoAlpha: 1, y: 0, duration: 1.1, ease: 'power3.out', stagger: 0.08, overwrite: true }),
        });
      }
    }, root);
    return () => ctx.revert();
  }, [scope]);
}
