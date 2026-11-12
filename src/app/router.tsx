import { useSyncExternalStore, type AnchorHTMLAttributes, type ReactNode } from 'react';
import type { IconName } from '../components/Icon';

/**
 * Minimal hash router (no dependency). The internal app lives under `#/app/...`;
 * any other hash (e.g. `#journey`) belongs to the landing page.
 */
export type PageKey =
  | 'dashboard' | 'karigars' | 'jobs' | 'issuance' | 'transfers' | 'production'
  | 'returns' | 'reconciliation' | 'investigation' | 'settlement' | 'reports';

export const PAGES: { key: PageKey; label: string; icon: IconName; group: 'Overview' | 'Custody' | 'Control' }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'grid', group: 'Overview' },
  { key: 'karigars', label: 'Karigars', icon: 'user', group: 'Overview' },
  { key: 'jobs', label: 'Jobs', icon: 'doc', group: 'Overview' },
  { key: 'issuance', label: 'Gold Issuance', icon: 'issue', group: 'Custody' },
  { key: 'transfers', label: 'Transfers', icon: 'transfer', group: 'Custody' },
  { key: 'production', label: 'Production', icon: 'manufacture', group: 'Custody' },
  { key: 'returns', label: 'Returns', icon: 'return', group: 'Custody' },
  { key: 'reconciliation', label: 'Reconciliation', icon: 'scale', group: 'Control' },
  { key: 'investigation', label: 'AI Investigation', icon: 'sparkle', group: 'Control' },
  { key: 'settlement', label: 'Settlement', icon: 'shield', group: 'Control' },
  { key: 'reports', label: 'Reports & Audit', icon: 'layers', group: 'Control' },
];

export interface Route {
  app: boolean;
  page: PageKey;
  id?: string;
  query: URLSearchParams;
}

function parse(hash: string): Route {
  const [path, qs = ''] = hash.replace(/^#/, '').split('?');
  const parts = path.split('/').filter(Boolean);
  const query = new URLSearchParams(qs);
  if (parts[0] !== 'app') return { app: false, page: 'dashboard', query };
  const page = (PAGES.find((p) => p.key === parts[1])?.key ?? 'dashboard') as PageKey;
  return { app: true, page, id: parts[2] ? decodeURIComponent(parts[2]) : undefined, query };
}

let current = parse(typeof window === 'undefined' ? '' : window.location.hash);
const subs = new Set<() => void>();
if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => {
    current = parse(window.location.hash);
    subs.forEach((s) => s());
  });
}

export function useRoute(): Route {
  return useSyncExternalStore(
    (l) => {
      subs.add(l);
      return () => {
        subs.delete(l);
      };
    },
    () => current,
  );
}

export const href = (page: PageKey, id?: string, query?: Record<string, string>) =>
  `#/app/${page}${id ? `/${encodeURIComponent(id)}` : ''}${query ? `?${new URLSearchParams(query)}` : ''}`;

export function navigate(page: PageKey, id?: string, query?: Record<string, string>) {
  window.location.hash = href(page, id, query);
}

export function Link({ to, id, query, children, ...rest }: { to: PageKey; id?: string; query?: Record<string, string>; children: ReactNode } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={href(to, id, query)} {...rest}>
      {children}
    </a>
  );
}
