import type { JSX, SVGProps } from 'react';

export type IconName =
  | 'issue' | 'transfer' | 'manufacture' | 'return' | 'reconcile'
  | 'layers' | 'scale' | 'sparkle' | 'shield'
  | 'arrow' | 'play' | 'search' | 'link' | 'doc' | 'user' | 'check' | 'alert'
  | 'chevron' | 'scan' | 'clock' | 'flame';

const PATHS: Record<IconName, JSX.Element> = {
  issue: (
    <>
      <path d="M4 16.5 8.2 9h11.6L24 16.5H4Z" />
      <path d="M2 23.5 6.2 16h15.6l4.2 7.5H2Z" />
      <path d="M10.5 12.5h7" opacity=".6" />
    </>
  ),
  transfer: (
    <>
      <path d="M4 9.5h19m0 0-4.5-4.5M23 9.5 18.5 14" />
      <path d="M24 18.5H5m0 0 4.5-4.5M5 18.5 9.5 23" />
    </>
  ),
  manufacture: (
    <>
      <circle cx="14" cy="14" r="3.6" />
      <path d="M14 3.5v3M14 21.5v3M3.5 14h3M21.5 14h3M6.6 6.6l2.1 2.1M19.3 19.3l2.1 2.1M6.6 21.4l2.1-2.1M19.3 8.7l2.1-2.1" />
      <circle cx="14" cy="14" r="7.6" opacity=".55" />
    </>
  ),
  return: (
    <>
      <path d="M14 3.5 24 9v10.5l-10 5.5-10-5.5V9l10-5.5Z" />
      <path d="M4 9l10 5.5L24 9M14 14.5V25" />
    </>
  ),
  reconcile: (
    <>
      <path d="M5 24V16M11 24V11M17 24V14M23 24V5" />
      <path d="M3 24.5h22" opacity=".5" />
    </>
  ),
  layers: (
    <>
      <path d="M14 3.5 25 9l-11 5.5L3 9l11-5.5Z" />
      <path d="M3 14l11 5.5L25 14" />
      <path d="M3 19l11 5.5L25 19" />
    </>
  ),
  scale: (
    <>
      <path d="M14 4v20M8 24h12M5 8h18" />
      <path d="M5 8 2 16a3.4 3.4 0 0 0 6 0L5 8ZM23 8l-3 8a3.4 3.4 0 0 0 6 0l-3-8Z" />
      <circle cx="14" cy="4" r="1.2" />
    </>
  ),
  sparkle: (
    <>
      <path d="M11 4c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7Z" />
      <path d="M21 15.5c.35 2.4 1.4 3.45 3.8 3.8-2.4.35-3.45 1.4-3.8 3.8-.35-2.4-1.4-3.45-3.8-3.8 2.4-.35 3.45-1.4 3.8-3.8Z" />
      <path d="M21.5 3.5v3M20 5h3" opacity=".7" />
    </>
  ),
  shield: (
    <>
      <path d="M14 3.5 23.5 7v7c0 5.6-4 9.4-9.5 10.5C8.5 23.4 4.5 19.6 4.5 14V7L14 3.5Z" />
      <path d="m9.5 14 3 3 6-6" />
    </>
  ),
  arrow: <path d="M5 14h18m0 0-6-6m6 6-6 6" />,
  play: (
    <>
      <circle cx="14" cy="14" r="10.5" />
      <path d="M12 10v8l6.2-4L12 10Z" />
    </>
  ),
  search: (
    <>
      <circle cx="12.5" cy="12.5" r="7.5" />
      <path d="m18 18 6 6" />
    </>
  ),
  link: (
    <>
      <path d="M12 16a5 5 0 0 0 7.1 0l3.5-3.5a5 5 0 0 0-7.1-7.1l-1.2 1.2" />
      <path d="M16 12a5 5 0 0 0-7.1 0l-3.5 3.5a5 5 0 0 0 7.1 7.1l1.2-1.2" />
    </>
  ),
  doc: (
    <>
      <path d="M7 3.5h9.5L22 9v15.5H7V3.5Z" />
      <path d="M16 3.5V9h6M10.5 14h8M10.5 18h8" />
    </>
  ),
  user: (
    <>
      <circle cx="14" cy="9.5" r="4.5" />
      <path d="M5 24c.9-4.6 4.3-7 9-7s8.1 2.4 9 7" />
    </>
  ),
  check: <path d="m6 14.5 5 5 11-11" />,
  alert: (
    <>
      <path d="M14 4 25 23H3L14 4Z" />
      <path d="M14 11v5.5M14 19.5v.5" />
    </>
  ),
  chevron: <path d="m9 11 5 5 5-5" />,
  scan: (
    <>
      <path d="M4 9V4h5M19 4h5v5M24 19v5h-5M9 24H4v-5" />
      <path d="M4 14h20" />
    </>
  ),
  clock: (
    <>
      <circle cx="14" cy="14" r="10" />
      <path d="M14 8.5V14l3.5 2.5" />
    </>
  ),
  flame: <path d="M14 3.5c1 4 6 6.5 6 12.5a6 6 0 0 1-12 0c0-2.6 1.3-4.4 2.6-5.6.2 2 1.2 3 2.4 3.3-.6-3.7.3-7.4 1-10.2Z" />,
};

interface Props extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
  /** use the shared gold gradient stroke instead of currentColor */
  gold?: boolean;
}

export function Icon({ name, size = 24, gold = false, strokeWidth = 1.5, ...rest }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      stroke={gold ? 'url(#ico-gold)' : 'currentColor'}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

/** Mount once: shared gradient referenced by gold icons. */
export function IconDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="ico-gold" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fbeec6" />
          <stop offset="0.45" stopColor="#e9bd68" />
          <stop offset="1" stopColor="#b47628" />
        </linearGradient>
      </defs>
    </svg>
  );
}
