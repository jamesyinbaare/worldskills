/** Parse "zoneId:quota" lines (or comma-separated) into quotaByZone. */
export function parseQuotaText(text: string): Record<string, number> | null {
  const lines = text
    .split(/[\n,]+/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return null;
  const out: Record<string, number> = {};
  for (const line of lines) {
    const [zoneId, raw] = line.split(":").map((p) => p.trim());
    const amount = Number(raw);
    if (!zoneId || !Number.isInteger(amount)) return null;
    out[zoneId] = amount;
  }
  return out;
}
