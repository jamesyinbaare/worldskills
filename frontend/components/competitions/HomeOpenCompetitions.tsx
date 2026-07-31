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

export function HomeOpenCompetitions() {
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
    <section
      id="competitions"
      className="bg-competitions-atmosphere scroll-mt-[var(--site-header-height)] border-t border-border px-4 py-16 sm:px-6 sm:py-20"
    >
      <div className={cn("mx-auto", skillMode ? "max-w-7xl" : "max-w-6xl")}>
        <header
          className={cn(
            "animate-comp-fade space-y-3",
            skillMode ? "mx-auto max-w-2xl text-center" : "max-w-2xl",
          )}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-blue/70">
            {skillMode
              ? `${activeCompetition.skills.length} open · ${activeCompetition.name}`
              : "Open now"}
          </p>
          <h2 className="text-2xl font-bold tracking-tight text-primary sm:text-3xl lg:text-4xl">
            {skillMode ? "Choose your skill area" : "Active competitions"}
          </h2>
          <p
            className={cn(
              "text-base leading-relaxed text-muted-foreground sm:text-lg",
              skillMode && "mx-auto max-w-lg",
            )}
          >
            {skillMode
              ? "Select a skill to review criteria and start registration."
              : "Choose a competition, pick your skill area, then register as a competitor."}
          </p>
        </header>

        {!skillMode ? (
          <div className="mt-8 h-px w-full bg-gradient-to-r from-brand-gold/80 via-border to-transparent" />
        ) : null}

        {loading ? (
          <p
            className={cn(
              "mt-10 text-sm text-muted-foreground",
              skillMode && "text-center",
            )}
            role="status"
          >
            {skillMode ? "Loading skill areas…" : "Loading competitions…"}
          </p>
        ) : null}

        {error ? (
          <p
            className={cn(
              "mt-10 text-sm text-destructive",
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
              "mt-10 max-w-md space-y-4",
              skillMode && "mx-auto text-center",
            )}
          >
            <p className="text-base text-muted-foreground">
              No competitions are open for registration right now. Check back
              soon, or sign in if you already have an account.
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
          <div className="mt-10 sm:mt-12">
            <SkillAreasCarousel
              competitionId={activeCompetition.competitionId}
              skills={activeCompetition.skills}
              footerHref={`/competitions/${activeCompetition.competitionId}/skills`}
            />
          </div>
        ) : null}

        {!loading && !skillMode && cycles.length > 0 ? (
          <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {cycles.map((cycle, index) => (
              <li key={cycle.competitionId} className="min-w-0">
                <CompetitionCard cycle={cycle} index={index} />
              </li>
            ))}
          </ul>
        ) : null}

        {!loading && !skillMode && cycles.length > 0 ? (
          <div className="mt-10">
            <Button variant="outline" className="min-h-11" asChild>
              <Link href="/competitions">Browse open competitions</Link>
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
