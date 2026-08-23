import Link from "next/link";
import { ArrowRightIcon, CalendarDaysIcon, TrophyIcon } from "lucide-react";
import type { OpenCompetitionOut } from "@/lib/api";
import { previewText } from "@/components/competitions/format";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { cn } from "@/lib/utils";

type CompetitionCardProps = {
  cycle: OpenCompetitionOut;
  index?: number;
};

const COVER_PALETTES = [
  {
    panel: "from-[#003764] via-[#0a4f8a] to-[#00853f]",
    glow: "bg-[#ffcc00]/25",
    accent: "text-[#ffcc00]",
  },
  {
    panel: "from-[#00853f] via-[#0a6b4a] to-[#003764]",
    glow: "bg-[#fee300]/20",
    accent: "text-[#fee300]",
  },
  {
    panel: "from-[#d51067] via-[#9e0c4e] to-[#003764]",
    glow: "bg-[#ff6c0c]/25",
    accent: "text-[#ffcc00]",
  },
  {
    panel: "from-[#ff6c0c] via-[#c44f08] to-[#003764]",
    glow: "bg-[#fee300]/20",
    accent: "text-white",
  },
  {
    panel: "from-[#003764] via-[#1a4f7a] to-[#d51067]",
    glow: "bg-[#00853f]/30",
    accent: "text-[#ffcc00]",
  },
] as const;

function coverPalette(competitionId: string) {
  let hash = 0;
  for (const char of competitionId) {
    hash = (hash + char.charCodeAt(0) * 17) % COVER_PALETTES.length;
  }
  return COVER_PALETTES[hash] ?? COVER_PALETTES[0];
}

function formatWindow(
  window?: { opensAt: string; closesAt: string } | null,
): string | null {
  if (!window) return null;
  const opens = new Date(window.opensAt);
  const closes = new Date(window.closesAt);
  if (Number.isNaN(opens.getTime()) || Number.isNaN(closes.getTime())) {
    return null;
  }
  const opts: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
  };
  return `${opens.toLocaleDateString(undefined, opts)} – ${closes.toLocaleDateString(undefined, opts)}`;
}

function windowYear(
  window?: { opensAt: string; closesAt: string } | null,
): string | null {
  if (!window?.opensAt) return null;
  const opens = new Date(window.opensAt);
  if (Number.isNaN(opens.getTime())) return null;
  return String(opens.getFullYear());
}

function registrationStatusLabel(
  cycle: OpenCompetitionOut,
): { title: string; detail: string } {
  if (cycle.registrationOpen) {
    return {
      title: "Registration",
      detail: formatWindow(cycle.window) ?? "Open for registration",
    };
  }
  if (cycle.window) {
    return {
      title: "Registration",
      detail: formatWindow(cycle.window)
        ? `Closed · ${formatWindow(cycle.window)}`
        : "Registration closed",
    };
  }
  return {
    title: "Registration",
    detail: "Registration closed",
  };
}

export function CompetitionCard({ cycle, index = 0 }: CompetitionCardProps) {
  const preview = previewText(cycle.description);
  const year = windowYear(cycle.window);
  const palette = coverPalette(cycle.competitionId);
  const registration = registrationStatusLabel(cycle);

  return (
    <Link
      href={`/competitions/${cycle.competitionId}`}
      data-testid="competition-card"
      className="animate-comp-fade group block h-full"
      style={{ animationDelay: `${0.08 * index}s` }}
    >
      <article
        className={cn(
          "flex h-full flex-col overflow-hidden rounded-3xl border border-border/70 bg-card shadow-[0_18px_40px_-28px_rgba(0,55,100,0.45)]",
          "transition-[transform,box-shadow] duration-300 ease-out",
          "hover:-translate-y-1 hover:shadow-[0_28px_50px_-24px_rgba(0,55,100,0.55)]",
        )}
      >
        <div
          className={cn(
            "relative aspect-4/5 overflow-hidden bg-linear-to-br",
            palette.panel,
          )}
          aria-hidden
        >
          <div
            className={cn(
              "absolute -top-16 -right-10 size-44 rounded-full blur-2xl transition-transform duration-500 group-hover:scale-110",
              palette.glow,
            )}
          />
          <div
            className={cn(
              "absolute -bottom-20 -left-12 size-52 rounded-full blur-3xl opacity-70",
              palette.glow,
            )}
          />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.18),transparent_42%)]" />
          <div className="absolute inset-x-0 bottom-0 h-1/3 bg-linear-to-t from-black/35 to-transparent" />

          <div className="absolute inset-0 flex flex-col justify-between p-5">
            <div className="flex items-start justify-between gap-3">
              <StatusBadge status={cycle.status} />
              {year ? (
                <span
                  className={cn(
                    "rounded-full bg-black/25 px-3 py-1 text-xs font-semibold tracking-[0.14em] uppercase backdrop-blur-sm",
                    palette.accent,
                  )}
                >
                  {year}
                </span>
              ) : null}
            </div>

            <div className="space-y-3">
              <span className="inline-flex size-12 items-center justify-center rounded-2xl bg-white/15 text-white shadow-sm ring-1 ring-white/25 backdrop-blur-sm">
                <TrophyIcon className="size-6" />
              </span>
              <h2 className="text-2xl font-bold leading-tight tracking-tight text-white drop-shadow-sm">
                {cycle.name}
              </h2>
            </div>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-4 p-5">
          <dl className="space-y-3 text-sm">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
                <CalendarDaysIcon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0">
                <dt className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {registration.title}
                </dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  {registration.detail}
                </dd>
              </div>
            </div>
          </dl>

          {preview ? (
            <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
              {preview}
            </p>
          ) : (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {cycle.registrationOpen
                ? "Explore skill areas and begin registration."
                : "Explore skill areas. Registration is closed."}
            </p>
          )}

          <div className="mt-auto flex items-center justify-between border-t border-border/70 pt-4">
            <span className="text-sm font-semibold text-foreground">
              View competition
            </span>
            <span className="inline-flex size-9 items-center justify-center rounded-full bg-brand-blue text-white transition-transform duration-300 group-hover:translate-x-0.5">
              <ArrowRightIcon className="size-4" aria-hidden />
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}
