/**
 * Custody nodes that ride the liquid-gold loop. `u` is the position along the
 * curve (see curve.ts). The front half of the loop runs u = 0.5 → 0, left to
 * right, which is the direction the gold flows.
 *
 * Values are illustrative demo figures, not live data.
 */
export type NodeIcon = 'issue' | 'transfer' | 'manufacture' | 'return' | 'reconcile';

export interface CustodyNode {
  id: NodeIcon;
  title: string;
  value: string;
  u: number;
}

export const CUSTODY_NODES: CustodyNode[] = [
  { id: 'issue', title: 'Issue', value: '100.000 g', u: 0.415 },
  { id: 'transfer', title: 'Transfer', value: '30.000 g', u: 0.33 },
  { id: 'manufacture', title: 'Manufacture', value: 'In progress', u: 0.215 },
  { id: 'return', title: 'Return', value: '99.436 g', u: 0.125 },
  { id: 'reconcile', title: 'Reconcile', value: 'Variance 0.564 g', u: 0.045 },
];

/** DOM label elements, registered by the HTML overlay and positioned by the scene each frame. */
export const nodeLabelEls: (HTMLElement | null)[] = [];

/**
 * Collision guard for the floating labels: a label hides when its card would overlap
 * any of the hero copy blocks, or slide under the fixed nav (minY, viewport px).
 * Registered by <Hero/>.
 */
export const labelSafe: { copyEls: HTMLElement[]; minY: number } = { copyEls: [], minY: 0 };
