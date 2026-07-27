"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightIcon,
  CalendarDaysIcon,
  SearchIcon,
  TrophyIcon,
} from "lucide-react";
import {
  ApiError,
  listInstitutionCompetitions,
  type InstitutionCompetitionOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

const COVER_PALETTES = [
  {
    panel:
      "from-[#003764] via-[#0a4f8a] to-[#00853f]",
    glow: "bg-[#ffcc00]/25",
    accent: "text-[#ffcc00]",
  },
  {
    panel:
      "from-[#00853f] via-[#0a6b4a] to-[#003764]",
    glow: "bg-[#fee300]/20",
    accent: "text-[#fee300]",
  },
  {
    panel:
      "from-[#d51067] via-[#9e0c4e] to-[#003764]",
    glow: "bg-[#ff6c0c]/25",
    accent: "text-[#ffcc00]",
  },
  {
    panel:
      "from-[#ff6c0c] via-[#c44f08] to-[#003764]",
    glow: "bg-[#fee300]/20",
    accent: "text-white",
  },
  {
    panel:
      "from-[#003764] via-[#1a4f7a] to-[#d51067]",
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

function formatPeriod(period: { start: string; end: string }): string {
  const start = new Date(period.start);
  const end = new Date(period.end);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return "Dates unavailable";
  }
  const opts: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    year: "numeric",
  };
  return `${start.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, opts)}`;
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

function periodYear(period: { start: string; end: string }): string | null {
  const start = new Date(period.start);
  if (Number.isNaN(start.getTime())) return null;
  return String(start.getFullYear());
}

function isCurrentCompetition(status: string): boolean {
  return status === "ACTIVE" || status === "LOCKED";
}

function CompetitionPortraitCard({
  competition,
}: {
  competition: InstitutionCompetitionOut;
}) {
  const current = isCurrentCompetition(competition.status);
  const windowLabel = formatWindow(competition.window);
  const year = periodYear(competition.period);
  const palette = coverPalette(competition.competitionId);

  return (
    <Link
      href={`/institution/competitions/${competition.competitionId}`}
      data-testid={`institution-competition-${competition.competitionId}`}
      className="group block h-full"
    >
      <article
        className={cn(
          "flex h-full flex-col overflow-hidden rounded-3xl border border-border/70 bg-card shadow-[0_18px_40px_-28px_rgba(0,55,100,0.45)]",
          "transition-[transform,box-shadow] duration-300 ease-out",
          "hover:-translate-y-1 hover:shadow-[0_28px_50px_-24px_rgba(0,55,100,0.55)]",
        )}
      >
        {/* Image placeholder — color field */}
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
              <StatusBadge status={competition.status} />
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
                {competition.name}
              </h2>
            </div>
          </div>
        </div>

        {/* Organized details */}
        <div className="flex flex-1 flex-col gap-4 p-5">
          <dl className="space-y-3 text-sm">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
                <CalendarDaysIcon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0">
                <dt className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  Competition period
                </dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  {formatPeriod(competition.period)}
                </dd>
              </div>
            </div>

            {windowLabel ? (
              <div className="rounded-2xl bg-muted/70 px-3.5 py-3">
                <dt className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  Registration window
                </dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  {windowLabel}
                </dd>
              </div>
            ) : null}
          </dl>

          {competition.description ? (
            <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
              {competition.description}
            </p>
          ) : (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {current
                ? "Browse skill areas and register competitors for your school."
                : "Review skill areas and your school’s roster history."}
            </p>
          )}

          <div className="mt-auto flex items-center justify-between border-t border-border/70 pt-4">
            <span className="text-sm font-semibold text-foreground">
              {current ? "Open competition" : "View details"}
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

export default function InstitutionCompetitionsPage() {
  const [competitions, setCompetitions] = useState<InstitutionCompetitionOut[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const rows = await listInstitutionCompetitions();
        if (cancelled) return;
        setCompetitions(rows);
        setLoadError(null);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setLoadError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredCompetitions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return competitions.filter((competition) => {
      if (statusFilter === "current" && !isCurrentCompetition(competition.status)) {
        return false;
      }
      if (statusFilter === "past" && competition.status !== "CLOSED") {
        return false;
      }
      if (
        !["all", "current", "past"].includes(statusFilter) &&
        competition.status !== statusFilter
      ) {
        return false;
      }
      if (
        query &&
        ![competition.name, competition.description ?? "", competition.status]
          .join(" ")
          .toLowerCase()
          .includes(query)
      ) {
        return false;
      }
      return true;
    });
  }, [competitions, search, statusFilter]);

  return (
    <PageShell width="wide" className="max-w-7xl space-y-8">
      <PageHeader
        title="Competitions"
        description="Browse current and past competitions, then open a competition to view skill areas and registrations."
      />

      <ApiErrorAlert error={loadError} title="Could not load competitions" />

      <Card>
        <CardContent className="grid gap-3 py-4 md:grid-cols-[minmax(0,2fr),240px]">
          <label className="relative block">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search competitions"
              className="h-11 pl-9"
              data-testid="institution-competitions-search"
            />
          </label>

          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger
              className="h-11 w-full"
              data-testid="institution-competitions-status-filter"
            >
              <SelectValue placeholder="All competitions" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All competitions</SelectItem>
              <SelectItem value="current">Current competitions</SelectItem>
              <SelectItem value="past">Past competitions</SelectItem>
              <SelectItem value="ACTIVE">Active</SelectItem>
              <SelectItem value="LOCKED">Locked</SelectItem>
              <SelectItem value="CLOSED">Closed</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading competitions…
        </p>
      ) : null}

      {!loading && filteredCompetitions.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-8 text-sm text-muted-foreground sm:text-center">
            No competitions match your search or filters.
          </CardContent>
        </Card>
      ) : null}

      <ul
        className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3"
        data-testid="institution-competitions-list"
      >
        {filteredCompetitions.map((competition) => (
          <li key={competition.competitionId} className="min-w-0">
            <CompetitionPortraitCard competition={competition} />
          </li>
        ))}
      </ul>
    </PageShell>
  );
}
