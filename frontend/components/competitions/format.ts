export function formatCompetitionDate(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.includes("T") ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatClosesAt(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function previewText(
  text: string | null | undefined,
  max = 140,
): string | null {
  if (!text?.trim()) return null;
  const cleaned = text.trim().replace(/\s+/g, " ");
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max).trimEnd()}…`;
}

export function registerPath(
  role: "competitor" | "institution",
  competitionId: string,
  skillId?: string | null,
): string {
  const base =
    role === "competitor"
      ? `/competitor/competitions/${competitionId}/register`
      : `/institution/competitions/${competitionId}/register`;
  if (!skillId) return base;
  return `${base}?skillId=${encodeURIComponent(skillId)}`;
}

export function loginNextHref(nextPath: string): string {
  return `/login?next=${encodeURIComponent(nextPath)}`;
}
