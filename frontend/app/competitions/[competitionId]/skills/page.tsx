"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeftIcon, SearchIcon } from "lucide-react";
import { useParams } from "next/navigation";
import {
  ApiError,
  getPublicCompetition,
  type PublicCompetitionOut,
} from "@/lib/api";
import { SkillAreaCard } from "@/components/competitions/SkillAreaCard";
import { previewText } from "@/components/competitions/format";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function formatWindow(
  window?: { opensAt: string; closesAt: string } | null,
): string | null {
  if (!window?.closesAt) return null;
  const closes = new Date(window.closesAt);
  if (Number.isNaN(closes.getTime())) return null;
  return `Registration closes ${closes.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })}`;
}

export default function CompetitionSkillsBrowsePage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [cycle, setCycle] = useState<PublicCompetitionOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await getPublicCompetition(competitionId);
        if (cancelled) return;
        setCycle(data);
        setError(null);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setError(err);
          setCycle(null);
        } else if (!cancelled) {
          setError(
            new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not load competition",
                fields: [],
                traceId: "",
              },
            }),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  const filtered = useMemo(() => {
    if (!cycle) return [];
    const q = query.trim().toLowerCase();
    if (!q) return cycle.skills;
    return cycle.skills.filter((skill) => {
      const haystack = [skill.name, skill.number, skill.familyName]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [cycle, query]);

  const blurb = previewText(cycle?.description, 180);
  const windowLabel = formatWindow(cycle?.window);
  const skillCount = cycle?.skills.length ?? 0;

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12 lg:py-16">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 mb-6 min-h-10 gap-1 text-muted-foreground"
          asChild
        >
          <Link href="/competitions">
            <ChevronLeftIcon className="size-4" aria-hidden />
            Competitions
          </Link>
        </Button>

        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading skill areas…
          </p>
        ) : null}

        <ApiErrorAlert error={error} title="Competition unavailable" />

        {error && !cycle ? (
          <Alert variant="destructive" className="mt-4">
            <AlertTitle>Not open for registration</AlertTitle>
            <AlertDescription>
              This competition is not available for public registration right
              now.
            </AlertDescription>
          </Alert>
        ) : null}

        {cycle ? (
          <div className="space-y-8 sm:space-y-10">
            <header className="animate-comp-fade max-w-2xl space-y-4">
              <div className="space-y-2">
                <p className="text-xs font-semibold tracking-[0.16em] text-brand-blue/70 uppercase">
                  Browse skill areas
                </p>
                <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl">
                  {cycle.name}
                </h1>
              </div>

              {blurb ? (
                <p className="max-w-2xl text-base leading-relaxed text-muted-foreground">
                  {blurb}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <span>
                  {skillCount} skill {skillCount === 1 ? "area" : "areas"}
                </span>
                {windowLabel ? (
                  <>
                    <span className="text-border" aria-hidden>
                      ·
                    </span>
                    <span>{windowLabel}</span>
                  </>
                ) : null}
              </div>
            </header>

            <div
              className="h-px w-full bg-linear-to-r from-brand-gold/80 via-border to-transparent"
              aria-hidden
            />

            {skillCount === 0 ? (
              <p className="text-base text-muted-foreground">
                No skill areas are open for this competition yet.
              </p>
            ) : (
              <div className="space-y-6">
                <div className="relative max-w-md">
                  <SearchIcon
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden
                  />
                  <Input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search skill areas…"
                    className="min-h-11 pl-9"
                    aria-label="Search skill areas"
                    data-testid="skill-areas-search"
                  />
                </div>

                {filtered.length === 0 ? (
                  <p className="text-sm text-muted-foreground" role="status">
                    No skill areas match “{query.trim()}”.
                  </p>
                ) : (
                  <ul
                    className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
                    data-testid="skill-areas-list"
                  >
                    {filtered.map((skill, index) => (
                      <li key={skill.skillId} className="min-w-0">
                        <SkillAreaCard
                          competitionId={competitionId}
                          skill={skill}
                          index={index}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
