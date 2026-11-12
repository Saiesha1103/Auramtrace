import { useMemo } from 'react';
import { useAppState } from './data/store';

/** Name lookups shared by pages. */
export function useLookups() {
  const s = useAppState();
  return useMemo(() => {
    const party = new Map(s.parties.map((p) => [p.id, p]));
    const job = new Map(s.jobs.map((j) => [j.id, j]));
    return {
      partyName: (id: string) => party.get(id)?.name ?? id,
      party: (id: string) => party.get(id),
      job: (id: string) => job.get(id),
      jobLabel: (id: string) => {
        const j = job.get(id);
        return j ? `${j.id} · ${j.title}` : id;
      },
    };
  }, [s.parties, s.jobs]);
}
