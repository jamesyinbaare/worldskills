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
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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
  const filteredCount = filtered.length;
  const searching = query.trim().length > 0;

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-14 lg:py-16">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 mb-8 min-h-10 gap-1 text-muted-foreground"
          asChild
        >
          <Link href="/competitions">
            <ChevronLeftIcon className="size-4" aria-hidden />
            Competitions
          </Link>
        </Button>

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

        {loading ? (
          <div className="space-y-10" role="status" aria-label="Loading skill areas">
            <div className="mx-auto max-w-2xl space-y-4 text-center">
              <Skeleton className="mx-auto h-3 w-40 rounded-full" />
              <Skeleton className="mx-auto h-10 w-72 rounded-xl sm:w-96" />
              <Skeleton className="mx-auto h-4 w-56 rounded-lg" />
            </div>
            <Skeleton className="mx-auto h-12 w-full max-w-md rounded-2xl" />
            <div className="grid gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-3">
              <Skeleton className="min-h-[22rem] rounded-[1.5rem]" />
              <Skeleton className="min-h-[22rem] rounded-[1.5rem]" />
              <Skeleton className="hidden min-h-[22rem] rounded-[1.5rem] lg:block" />
            </div>
          </div>
        ) : null}

        {cycle ? (
          <div className="space-y-10 sm:space-y-12">
            <header className="animate-comp-fade mx-auto max-w-2xl space-y-4 text-center">
              <p className="text-xs font-semibold tracking-[0.16em] text-brand-blue/70 uppercase">
                {skillCount} open · {cycle.name}
              </p>
              <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl lg:text-5xl">
                Choose your skill area
              </h1>
              <p className="mx-auto max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg">
                {blurb ||
                  "Select a skill to review criteria and start registration."}
              </p>
              {windowLabel ? (
                <p className="text-sm text-muted-foreground">{windowLabel}</p>
              ) : null}
            </header>

            {skillCount === 0 ? (
              <p className="mx-auto max-w-md text-center text-base text-muted-foreground">
                No skill areas are open for this competition yet.
              </p>
            ) : (
              <div className="space-y-8">
                <div className="mx-auto flex w-full max-w-md flex-col gap-3">
                  <div className="relative">
                    <SearchIcon
                      className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    />
                    <Input
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search skill areas…"
                      className="min-h-12 rounded-2xl border-border/70 bg-card/80 pl-10 shadow-sm"
                      aria-label="Search skill areas"
                      data-testid="skill-areas-search"
                    />
                  </div>
                  <p
                    className="text-center text-sm text-muted-foreground"
                    role="status"
                  >
                    {searching
                      ? `${filteredCount} of ${skillCount} skill ${skillCount === 1 ? "area" : "areas"}`
                      : `${skillCount} skill ${skillCount === 1 ? "area" : "areas"}`}
                  </p>
                </div>

                {filtered.length === 0 ? (
                  <div className="mx-auto max-w-md space-y-3 py-8 text-center">
                    <p className="text-base text-muted-foreground" role="status">
                      No skill areas match “{query.trim()}”.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 rounded-2xl"
                      onClick={() => setQuery("")}
                    >
                      Clear search
                    </Button>
                  </div>
                ) : (
                  <ul
                    className={cn(
                      "mx-auto grid gap-5 sm:gap-6",
                      filteredCount === 1 && "max-w-md grid-cols-1",
                      filteredCount === 2 &&
                        "max-w-3xl grid-cols-1 sm:grid-cols-2",
                      filteredCount === 3 &&
                        "max-w-5xl grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
                      filteredCount >= 4 &&
                        "max-w-6xl grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
                    )}
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
