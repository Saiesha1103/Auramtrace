import { useEffect } from 'react';
import { IconDefs } from './components/Icon';
import { Nav } from './components/Nav';
import { Hero } from './sections/Hero';
import { FeatureStrip } from './sections/FeatureStrip';
import { GoldJourney } from './sections/GoldJourney';
import { ProductPreview } from './sections/ProductPreview';
import { AIInvestigation } from './sections/AIInvestigation';
import { FinalCTA } from './sections/FinalCTA';
import { useReducedMotion } from './lib/useReducedMotion';
import { useSmoothScroll } from './lib/useSmoothScroll';
import { ScrollTrigger } from './lib/motion';

export function App() {
  const reduced = useReducedMotion();
  useSmoothScroll(!reduced);

  // fonts change line metrics; re-measure pinned sections once they land
  useEffect(() => {
    document.fonts?.ready.then(() => ScrollTrigger.refresh());
  }, []);

  return (
    <>
      <IconDefs />
      <a className="sr-only" href="#journey">
        Skip to content
      </a>
      <Nav />
      <main>
        <Hero />
        <FeatureStrip />
        <GoldJourney />
        <ProductPreview />
        <AIInvestigation />
        <FinalCTA />
      </main>
    </>
  );
}
