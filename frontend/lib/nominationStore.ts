/** Client-side nomination list until a GET list API exists. */

export type NominationRow = {
  nominationId: string;
  status: string;
  skillId?: string;
  competitorRef?: string;
  institutionId?: string;
  reason?: string | null;
};

function key(competitionId: string): string {
  return `scms_nominations_${competitionId}`;
}

function getSessionStorage(): Storage | null {
  try {
    const ss = globalThis.sessionStorage;
    if (!ss) return null;
    return ss;
  } catch {
    return null;
  }
}

export function loadNominations(competitionId: string): NominationRow[] {
  const ss = getSessionStorage();
  if (!ss) return [];
  try {
    const raw = ss.getItem(key(competitionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as NominationRow[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveNominations(competitionId: string, rows: NominationRow[]): void {
  const ss = getSessionStorage();
  if (!ss) return;
  ss.setItem(key(competitionId), JSON.stringify(rows));
}

export function upsertNomination(
  competitionId: string,
  row: NominationRow,
): NominationRow[] {
  const prev = loadNominations(competitionId);
  const idx = prev.findIndex((n) => n.nominationId === row.nominationId);
  const next =
    idx >= 0
      ? prev.map((n, i) => (i === idx ? { ...n, ...row } : n))
      : [row, ...prev];
  saveNominations(competitionId, next);
  return next;
}
