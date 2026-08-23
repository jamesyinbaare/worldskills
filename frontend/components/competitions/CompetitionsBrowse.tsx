"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  formatApiNetworkError,
  getPublicCompetition,
  getPublicSettings,
  listOpenCompetitions,
  type OpenCompetitionOut,
  type PublicCompetitionOut,
  type SystemSettingsOut,
} from "@/lib/api";
import { CompetitionCard } from "@/components/competitions/CompetitionCard";
import { SkillAreasCarousel } from "@/components/competitions/SkillAreasCarousel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CompetitionsBrowse() {
  const [cycles, setCycles] = useState<OpenCompetitionOut[]>([]);
  const [settings, setSettings] = useState<SystemSettingsOut | null>(null);
  const [activeCompetition, setActiveCompetition] =
    useState<PublicCompetitionOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const [items, sys] = await Promise.all([
          listOpenCompetitions(),
          getPublicSettings(),
        ]);
        if (cancelled) return;
        setCycles(items);
        setSettings(sys);
        setError(null);

        const showSkills =
          !sys.allowMultipleActiveCompetitions && items.length === 1;
        if (showSkills) {
          const detail = await getPublicCompetition(items[0].competitionId);
          if (!cancelled) setActiveCompetition(detail);
        } else if (!cancelled) {
          setActiveCompetition(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            formatApiNetworkError(err, "Could not load open competitions."),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const skillMode =
    settings != null &&
    !settings.allowMultipleActiveCompetitions &&
    cycles.length === 1 &&
    activeCompetition != null;

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div
        className={cn(
          "mx-auto px-4 py-12 sm:px-6 sm:py-16 lg:py-20",
          skillMode ? "max-w-7xl" : "max-w-6xl",
        )}
      >
        <header
          className={cn(
            "animate-comp-fade space-y-3",
            skillMode ? "mx-auto max-w-2xl text-center" : "max-w-2xl",
          )}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-blue/70">
            {skillMode
              ? `${activeCompetition.skills.length} skill ${activeCompetition.skills.length === 1 ? "area" : "areas"} · ${activeCompetition.name}`
              : "WorldSkills Ghana"}
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl lg:text-5xl">
            {skillMode ? "Choose your skill area" : "Competitions"}
          </h1>
          <p
            className={cn(
              "text-base leading-relaxed text-muted-foreground sm:text-lg",
              skillMode && "mx-auto max-w-lg",
            )}
          >
            {skillMode
              ? activeCompetition.registrationOpen
                ? "Select a skill to review criteria and start registration."
                : "Select a skill to review criteria. Registration is closed."
              : "Browse competitions and skill areas. Register when the window is open."}
          </p>
        </header>

        {!skillMode ? (
          <div className="mt-10 h-px w-full bg-gradient-to-r from-brand-gold/80 via-border to-transparent" />
        ) : null}

        {loading ? (
          <p
            className={cn(
              "mt-12 text-sm text-muted-foreground",
              skillMode && "text-center",
            )}
            role="status"
          >
            Loading…
          </p>
        ) : null}

        {error ? (
          <p
            className={cn(
              "mt-12 text-sm text-destructive",
              skillMode && "text-center",
            )}
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {!loading && !error && cycles.length === 0 ? (
          <div
            className={cn(
              "mt-12 max-w-md space-y-4",
              skillMode && "mx-auto text-center",
            )}
          >
            <p className="text-base text-muted-foreground">
              No active competitions are available right now. Check back soon,
              or sign in if you already have an account.
            </p>
            <div
              className={cn(
                "flex flex-wrap gap-2",
                skillMode && "justify-center",
              )}
            >
              <Button variant="outline" className="min-h-11" asChild>
                <Link href="/login">Login</Link>
              </Button>
              <Button variant="accent" className="min-h-11" asChild>
                <Link href="/signup">Register</Link>
              </Button>
            </div>
          </div>
        ) : null}

        {!loading && skillMode ? (
          <div className="mt-12">
            <SkillAreasCarousel
              competitionId={activeCompetition.competitionId}
              skills={activeCompetition.skills}
              footerHref={`/competitions/${activeCompetition.competitionId}/skills`}
              registrationOpen={activeCompetition.registrationOpen !== false}
            />
          </div>
        ) : null}

        {!loading && !skillMode && cycles.length > 0 ? (
          <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {cycles.map((cycle, index) => (
              <li key={cycle.competitionId} className="min-w-0">
                <CompetitionCard cycle={cycle} index={index} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
