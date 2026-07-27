"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, listOpenCompetitions, type OpenCompetitionOut } from "@/lib/api";
import { CompetitionCard } from "@/components/competitions/CompetitionCard";
import { Button } from "@/components/ui/button";

export function HomeOpenCompetitions() {
  const [cycles, setCycles] = useState<OpenCompetitionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const items = await listOpenCompetitions();
        if (!cancelled) {
          setCycles(items);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load open competitions.",
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

  return (
    <section
      id="competitions"
      className="bg-competitions-atmosphere scroll-mt-[var(--site-header-height)] border-t border-border px-4 py-16 sm:px-6 sm:py-20"
    >
      <div className="mx-auto max-w-6xl">
        <header className="animate-comp-fade max-w-2xl space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-blue/70">
            Open now
          </p>
          <h2 className="text-2xl font-bold tracking-tight text-primary sm:text-3xl lg:text-4xl">
            Active competitions
          </h2>
          <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
            Choose a competition, pick your skill area, then register as a
            competitor or through your institution.
          </p>
        </header>

        <div className="mt-8 h-px w-full bg-gradient-to-r from-brand-gold/80 via-border to-transparent" />

        {loading ? (
          <p className="mt-10 text-sm text-muted-foreground" role="status">
            Loading competitions…
          </p>
        ) : null}

        {error ? (
          <p className="mt-10 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {!loading && !error && cycles.length === 0 ? (
          <div className="mt-10 max-w-md space-y-4">
            <p className="text-base text-muted-foreground">
              No competitions are open for registration right now. Check back
              soon, or sign in if you already have an account.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="min-h-11" asChild>
                <Link href="/login">Login</Link>
              </Button>
              <Button variant="accent" className="min-h-11" asChild>
                <Link href="/signup">Register</Link>
              </Button>
            </div>
          </div>
        ) : null}

        {!loading && cycles.length > 0 ? (
          <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {cycles.map((cycle, index) => (
              <li key={cycle.competitionId} className="min-w-0">
                <CompetitionCard cycle={cycle} index={index} />
              </li>
            ))}
          </ul>
        ) : null}

        {!loading && cycles.length > 0 ? (
          <p className="mt-10 text-center">
            <Link
              href="/competitions"
              className="text-sm font-semibold text-primary underline-offset-4 hover:underline"
            >
              Browse all open competitions
            </Link>
          </p>
        ) : null}
      </div>
    </section>
  );
}
