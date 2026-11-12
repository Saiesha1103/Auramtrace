import { useRef } from 'react';
import { Icon, type IconName } from '../components/Icon';
import { useReveal } from '../lib/useReveal';
import './FeatureStrip.css';

const FEATURES: { icon: IconName; title: string; body: string }[] = [
  { icon: 'layers', title: 'End-to-End Traceability', body: 'From issue to final return.' },
  { icon: 'scale', title: 'Accurate Reconciliation', body: 'Fine-gold-equivalent accounting.' },
  { icon: 'sparkle', title: 'AI Investigation', body: 'Evidence-backed discrepancy explanations.' },
  { icon: 'shield', title: 'Transparent Settlement', body: 'Clear and auditable records.' },
];

export function FeatureStrip() {
  const root = useRef<HTMLElement>(null);
  useReveal(root);
  return (
    <section ref={root} id="platform" className="features" aria-label="Platform highlights">
      <div className="features-rule" aria-hidden="true" />
      <ul className="features-list container">
        {FEATURES.map((f) => (
          <li key={f.title} className="feature" data-reveal>
            <span className="feature-icon">
              <Icon name={f.icon} size={34} gold strokeWidth={1.3} />
            </span>
            <span className="feature-text">
              <strong>{f.title}</strong>
              <span>{f.body}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
