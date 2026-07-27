"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import {
  ApiError,
  getPublicCompetition,
  isCompetitorRole,
  listMyRegistrations,
  type PublicCompetitionOut,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  formatCompetitionDate,
  loginNextHref,
  registerPath,
} from "@/components/competitions/format";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

function EnterContent() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const searchParams = useSearchParams();
  const skillIdParam = searchParams.get("skillId");
  const { status, me } = useAuth();

  const [cycle, setCycle] = useState<PublicCompetitionOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await getPublicCompetition(competitionId);
        if (!cancelled) {
          setCycle(data);
          setError(null);
        }
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

  useEffect(() => {
    if (status !== "authenticated" || !isCompetitorRole(me?.role ?? "")) {
      setAlreadyRegistered(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        setAlreadyRegistered(
          rows.some((r) => r.competitionId === competitionId),
        );
      } catch {
        if (!cancelled) setAlreadyRegistered(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, me?.role, competitionId]);

  const selectedSkill = useMemo(() => {
    if (!cycle) return null;
    if (skillIdParam) {
      return (
        cycle.skills.find((s) => s.skillId === skillIdParam) ??
        (cycle.skills.length === 1 ? cycle.skills[0] : null)
      );
    }
    return cycle.skills.length === 1 ? cycle.skills[0] : null;
  }, [cycle, skillIdParam]);

  const effectiveSkillId = selectedSkill?.skillId ?? skillIdParam;

  const competitorRegister = registerPath(
    "competitor",
    competitionId,
    effectiveSkillId,
  );
  const institutionRegister = registerPath(
    "institution",
    competitionId,
    effectiveSkillId,
  );
  const competitorDashboard = `/competitor/competitions/${competitionId}`;

  const competitorHref = alreadyRegistered
    ? competitorDashboard
    : status === "authenticated"
      ? competitorRegister
      : loginNextHref(competitorRegister);
  const institutionHref =
    status === "authenticated"
      ? institutionRegister
      : loginNextHref(institutionRegister);

  const skillsBack =
    cycle && cycle.skills.length >= 2
      ? `/competitions/${competitionId}/skills`
      : "/competitions";

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Button variant="link" className="h-auto min-h-11 px-0" asChild>
          <Link href={skillsBack}>
            ←{" "}
            {cycle && cycle.skills.length >= 2
              ? "Back to skill areas"
              : "Back to competitions"}
          </Link>
        </Button>

        {loading ? (
          <p className="mt-8 text-sm text-muted-foreground" role="status">
            Loading…
          </p>
        ) : null}

        <ApiErrorAlert error={error} title="Competition unavailable" />

        {error && !cycle ? (
          <Alert variant="destructive" className="mt-6">
            <AlertTitle>Not open for registration</AlertTitle>
            <AlertDescription>
              This competition is not available for public registration right
              now.
            </AlertDescription>
          </Alert>
        ) : null}

        {cycle ? (
          <div className="animate-comp-fade mt-6 space-y-10">
            <header className="space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-blue/70">
                Begin registration
              </p>
              <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl">
                {cycle.name}
              </h1>
              <p className="text-sm text-muted-foreground sm:text-base">
                {formatCompetitionDate(cycle.period.start)} →{" "}
                {formatCompetitionDate(cycle.period.end)}
                {cycle.window?.closesAt
                  ? ` · Registration closes ${formatCompetitionDate(cycle.window.closesAt)}`
                  : null}
              </p>
            </header>

            {cycle.description?.trim() ? (
              <section className="space-y-3" aria-labelledby="about-heading">
                <h2
                  id="about-heading"
                  className="text-lg font-semibold tracking-tight text-foreground"
                >
                  About this competition
                </h2>
                <div className="whitespace-pre-wrap text-base leading-relaxed text-foreground/90">
                  {cycle.description}
                </div>
              </section>
            ) : null}

            {selectedSkill ? (
              <section
                className="rounded-2xl bg-card p-5 ring-1 ring-border"
                aria-labelledby="selected-skill-heading"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Selected skill area
                </p>
                <h2
                  id="selected-skill-heading"
                  className="mt-2 text-xl font-bold tracking-tight text-primary"
                >
                  {selectedSkill.name}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[
                    selectedSkill.number && `Skill ${selectedSkill.number}`,
                    selectedSkill.familyName,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </section>
            ) : null}

            <section className="space-y-4 rounded-2xl bg-card p-6 ring-1 ring-border">
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-foreground">
                  How are you entering?
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {alreadyRegistered
                    ? "You are already registered for this competition. Open your dashboard to continue."
                    : "Sign in or create an account if needed, then complete the registration form."}
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Button
                  size="lg"
                  className="min-h-11 flex-1"
                  asChild
                  data-testid="register-as-competitor"
                >
                  <Link href={competitorHref}>
                    {alreadyRegistered
                      ? "Go to my competition"
                      : "Register as competitor"}
                  </Link>
                </Button>
                {!alreadyRegistered ? (
                  <Button
                    size="lg"
                    variant="outline"
                    className="min-h-11 flex-1"
                    asChild
                    data-testid="register-as-institution"
                  >
                    <Link href={institutionHref}>Register as institution</Link>
                  </Button>
                ) : null}
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function CompetitionEnterPage() {
  return (
    <Suspense
      fallback={
        <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))] px-4 py-16 text-sm text-muted-foreground">
          Loading…
        </div>
      }
    >
      <EnterContent />
    </Suspense>
  );
}
