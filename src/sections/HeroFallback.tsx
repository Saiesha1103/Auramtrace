import './HeroFallback.css';

/**
 * Pure SVG/CSS poster of the hero scene. Shown instantly while three.js
 * streams in, and kept as the visual when WebGL is unavailable.
 */
export function HeroFallback({ dimmed, animate }: { dimmed: boolean; animate: boolean }) {
  return (
    <div className={`hero-fallback ${dimmed ? 'is-dimmed' : ''} ${animate ? 'is-animated' : ''}`}>
      <svg className="hf-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="hf-gold" x1="0" y1="0" x2="1" y2="0.3">
            <stop offset="0" stopColor="#6b3f12" />
            <stop offset="0.25" stopColor="#f2d48e" />
            <stop offset="0.45" stopColor="#b97a2a" />
            <stop offset="0.62" stopColor="#fff1c8" />
            <stop offset="0.8" stopColor="#c48a32" />
            <stop offset="1" stopColor="#7a4a16" />
          </linearGradient>
          <radialGradient id="hf-nugget" cx="0.4" cy="0.35" r="0.7">
            <stop offset="0" stopColor="#fff4cf" />
            <stop offset="0.35" stopColor="#e9b95e" />
            <stop offset="0.75" stopColor="#8f5a1c" />
            <stop offset="1" stopColor="#3b220a" />
          </radialGradient>
          <radialGradient id="hf-glow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stopColor="#ffb54d" stopOpacity="0.55" />
            <stop offset="1" stopColor="#ffb54d" stopOpacity="0" />
          </radialGradient>
          <filter id="hf-blur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="14" />
          </filter>
        </defs>

        <ellipse cx="1080" cy="560" rx="520" ry="360" fill="url(#hf-glow)" />

        {/* platform */}
        <g opacity="0.9">
          <ellipse cx="1080" cy="720" rx="300" ry="54" fill="none" stroke="#e2b35c" strokeOpacity="0.55" strokeWidth="2" />
          <ellipse cx="1080" cy="720" rx="220" ry="38" fill="none" stroke="#f2d48e" strokeOpacity="0.4" />
          <ellipse cx="1080" cy="720" rx="120" ry="20" fill="#ffcf7a" fillOpacity="0.35" filter="url(#hf-blur)" />
          <ellipse cx="1080" cy="735" rx="330" ry="60" fill="#120c06" fillOpacity="0.6" />
          <path d="M990 720 1020 470h120l30 250" fill="#ffc46a" fillOpacity="0.08" />
        </g>

        {/* infinity ribbon */}
        <g className="hf-ribbon">
          <path
            className="hf-glow"
            d="M120 820C420 760 600 560 820 470 1040 380 1180 640 1380 600 1560 560 1560 300 1400 250 1220 190 1020 380 900 470 760 570 520 700 120 820Z"
            fill="none"
            stroke="#ffb347"
            strokeOpacity="0.35"
            strokeWidth="30"
            filter="url(#hf-blur)"
          />
          <path
            className="hf-flow"
            d="M120 820C420 760 600 560 820 470 1040 380 1180 640 1380 600 1560 560 1560 300 1400 250 1220 190 1020 380 900 470 760 570 520 700 120 820Z"
            fill="none"
            stroke="url(#hf-gold)"
            strokeWidth="18"
            strokeLinecap="round"
          />
          <path
            className="hf-flow hf-flow-2"
            d="M140 800C430 735 610 540 830 455 1050 370 1190 625 1385 585 1545 548 1540 318 1405 268"
            fill="none"
            stroke="#fff1c8"
            strokeOpacity="0.7"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </g>

        {/* nugget */}
        <g className="hf-nugget">
          <path
            d="M1030 470c18-34 62-52 98-36 30 13 52 40 46 74-6 32-30 54-62 60-36 7-72-6-88-34-11-20-6-44 6-64Z"
            fill="url(#hf-nugget)"
          />
          <path d="M1060 455c20-10 44-8 60 4" stroke="#fff6da" strokeOpacity="0.8" strokeWidth="3" fill="none" strokeLinecap="round" />
        </g>
      </svg>
    </div>
  );
}
