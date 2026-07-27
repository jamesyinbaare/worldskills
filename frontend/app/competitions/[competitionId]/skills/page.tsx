"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeftIcon } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
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

export default function CompetitionSkillsPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const router = useRouter();
  const [cycle, setCycle] = useState<PublicCompetitionOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await getPublicCompetition(competitionId);
        if (cancelled) return;
        if (data.skills.length < 2) {
          const sole = data.skills[0]?.skillId;
          const qs = sole ? `?skillId=${encodeURIComponent(sole)}` : "";
          router.replace(`/competitions/${competitionId}/enter${qs}`);
          return;
        }
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
  }, [competitionId, router]);

  const blurb = previewText(cycle?.description, 180);
  const windowLabel = formatWindow(cycle?.window);
  const skillCount = cycle?.skills.length ?? 0;

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-12 lg:py-16">
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
            <header className="animate-comp-fade space-y-4">
              <div className="space-y-2">
                <p className="text-xs font-semibold tracking-[0.16em] text-brand-blue/70 uppercase">
                  Choose a skill area
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

            <ul className="space-y-3 sm:space-y-4">
              {cycle.skills.map((skill, index) => (
                <li key={skill.skillId} className="min-w-0">
                  <SkillAreaCard
                    competitionId={competitionId}
                    skill={skill}
                    index={index}
                  />
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
