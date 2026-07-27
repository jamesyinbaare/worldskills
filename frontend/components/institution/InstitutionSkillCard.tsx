import Link from "next/link";
import { DownloadIcon, UserPlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type InstitutionSkillCardProps = {
  competitionId: string;
  skillId: string;
  skillName: string;
  familyName?: string | null;
  number?: string | null;
  quota?: {
    max: number;
    used: number;
    remaining: number;
    configured: boolean;
  } | null;
  registrationEnabled?: boolean;
  disabledLabel?: string;
  index?: number;
  hasCriteriaDocument?: boolean;
  onDownloadCriteria?: () => void;
  criteriaDownloadPending?: boolean;
};

const SKILL_PALETTES = [
  {
    panel: "from-[#003764] via-[#0a4f8a] to-[#1a6aa8]",
    glow: "bg-[#ffcc00]/25",
    soft: "bg-brand-blue/10 text-brand-blue",
    bar: "bg-brand-blue",
  },
  {
    panel: "from-[#00853f] via-[#0a6b4a] to-[#0d7a55]",
    glow: "bg-[#fee300]/20",
    soft: "bg-brand-green/10 text-brand-green",
    bar: "bg-brand-green",
  },
  {
    panel: "from-[#d51067] via-[#9e0c4e] to-[#b3125a]",
    glow: "bg-[#ff6c0c]/25",
    soft: "bg-brand-magenta/10 text-brand-magenta",
    bar: "bg-brand-magenta",
  },
  {
    panel: "from-[#ff6c0c] via-[#d85a08] to-[#c44f08]",
    glow: "bg-[#fee300]/20",
    soft: "bg-brand-orange/10 text-brand-orange",
    bar: "bg-brand-orange",
  },
] as const;

function skillPalette(skillId: string, index: number) {
  let hash = index;
  for (const char of skillId) {
    hash = (hash + char.charCodeAt(0) * 13) % SKILL_PALETTES.length;
  }
  return SKILL_PALETTES[hash] ?? SKILL_PALETTES[0];
}

export function InstitutionSkillCard({
  competitionId,
  skillId,
  skillName,
  familyName,
  number,
  quota,
  registrationEnabled = true,
  disabledLabel = "Registration unavailable",
  index = 0,
  hasCriteriaDocument = false,
  onDownloadCriteria,
  criteriaDownloadPending = false,
}: InstitutionSkillCardProps) {
  const registerHref = `/institution/competitions/${competitionId}/register?skillId=${encodeURIComponent(skillId)}`;
  const hasQuotaSpace = !quota?.configured || quota.remaining > 0;
  const canRegister = registrationEnabled && hasQuotaSpace;
  const palette = skillPalette(skillId, index);
  const usedPct =
    quota?.configured && quota.max > 0
      ? Math.min(100, Math.round((quota.used / quota.max) * 100))
      : 0;

  return (
    <article
      className={cn(
        "group flex h-full flex-col overflow-hidden rounded-3xl border border-border/70 bg-card shadow-[0_16px_36px_-28px_rgba(0,55,100,0.45)]",
        "transition-[transform,box-shadow] duration-300 ease-out",
        "hover:-translate-y-1 hover:shadow-[0_24px_44px_-24px_rgba(0,55,100,0.55)]",
        !canRegister && "opacity-90",
      )}
      data-testid="institution-skill-card"
      style={{ animationDelay: `${0.05 * index}s` }}
    >
      <div
        className={cn(
          "relative h-28 overflow-hidden bg-linear-to-br",
          palette.panel,
        )}
        aria-hidden
      >
        <div
          className={cn(
            "absolute -top-10 -right-8 size-28 rounded-full blur-2xl transition-transform duration-500 group-hover:scale-110",
            palette.glow,
          )}
        />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_20%,rgba(255,255,255,0.22),transparent_45%)]" />
        <div className="absolute inset-0 flex items-end justify-between p-4">
          <span className="inline-flex rounded-full bg-black/25 px-3 py-1 text-[0.7rem] font-semibold tracking-[0.14em] text-white uppercase backdrop-blur-sm">
            {familyName?.trim() || "Skill area"}
          </span>
          {number ? (
            <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-white/15 text-sm font-bold text-white ring-1 ring-white/25 backdrop-blur-sm">
              {number}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-5">
        <div className="space-y-1.5">
          <h3 className="text-lg font-bold leading-snug tracking-tight text-foreground">
            {skillName}
          </h3>
          {number ? (
            <p className="text-sm text-muted-foreground">Skill {number}</p>
          ) : null}
        </div>

        {quota?.configured ? (
          <div className="space-y-2 rounded-2xl bg-muted/70 px-3.5 py-3">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-foreground">
                {quota.remaining} of {quota.max} slots left
              </span>
              <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", palette.soft)}>
                {quota.used} used
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-border/80">
              <div
                className={cn("h-full rounded-full transition-[width] duration-500", palette.bar)}
                style={{ width: `${usedPct}%` }}
              />
            </div>
            <span className="sr-only" data-testid={`quota-remaining-${skillId}`}>
              {quota.remaining}
            </span>
          </div>
        ) : quota ? (
          <div className="rounded-2xl border border-dashed border-border/80 px-3.5 py-3 text-sm text-muted-foreground">
            Quota not configured for this skill yet.
          </div>
        ) : (
          <div className="rounded-2xl bg-muted/70 px-3.5 py-3 text-sm text-muted-foreground">
            Register competitors into this skill area.
          </div>
        )}

        <div className="mt-auto space-y-2 pt-1">
          {hasCriteriaDocument && onDownloadCriteria ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full gap-2 rounded-2xl"
              disabled={criteriaDownloadPending}
              onClick={onDownloadCriteria}
              data-testid={`download-criteria-${skillId}`}
            >
              <DownloadIcon className="size-4" aria-hidden />
              {criteriaDownloadPending ? "Downloading…" : "Download criteria"}
            </Button>
          ) : null}
          {canRegister ? (
            <Button className="min-h-11 w-full gap-2 rounded-2xl" asChild>
              <Link
                href={registerHref}
                data-testid={`register-skill-${skillId}`}
              >
                <UserPlusIcon className="size-4" aria-hidden />
                Register
              </Link>
            </Button>
          ) : (
            <Button className="min-h-11 w-full rounded-2xl" disabled>
              {registrationEnabled ? "Quota full" : disabledLabel}
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}
