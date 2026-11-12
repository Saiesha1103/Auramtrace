import { useEffect, useState, type RefObject } from 'react';

/** True while the element is within (or near) the viewport. */
export function useInView(ref: RefObject<Element | null>, rootMargin = '120px') {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, rootMargin]);
  return inView;
}
