"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  ApiError,
  getPublicCompetition,
  isCompetitorRole,
  listMyRegistrations,
  type PublicCompetitionOut,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  registerPath,
  signupNextHref,
} from "@/components/competitions/format";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * Legacy entry URL. When a skill is selected, skip the chooser and send
 * competitors straight to signup (or the registration form if signed in).
 */
function EnterContent() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const searchParams = useSearchParams();
  const skillIdParam = searchParams.get("skillId");
  const router = useRouter();
  const { status, me } = useAuth();

  const [cycle, setCycle] = useState<PublicCompetitionOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);
  const [checkedRegistration, setCheckedRegistration] = useState(false);

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
    if (status === "loading") return;
    if (status !== "authenticated" || !isCompetitorRole(me?.role ?? "")) {
      setAlreadyRegistered(false);
      setCheckedRegistration(true);
      return;
    }
    let cancelled = false;
    setCheckedRegistration(false);
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        setAlreadyRegistered(
          rows.some((r) => r.competitionId === competitionId),
        );
      } catch {
        if (!cancelled) setAlreadyRegistered(false);
      } finally {
        if (!cancelled) setCheckedRegistration(true);
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
  const competitorDashboard = `/competitor/competitions/${competitionId}`;

  const destination = useMemo(() => {
    if (alreadyRegistered) return competitorDashboard;
    if (status === "authenticated" && isCompetitorRole(me?.role ?? "")) {
      return competitorRegister;
    }
    return signupNextHref(competitorRegister);
  }, [
    alreadyRegistered,
    competitorDashboard,
    competitorRegister,
    me?.role,
    status,
  ]);

  useEffect(() => {
    if (loading || error || !cycle || status === "loading") return;
    if (!checkedRegistration) return;
    // Prefer skill browse when multiple skills and none selected
    if (!effectiveSkillId && cycle.skills.length >= 1) {
      router.replace(`/competitions/${competitionId}/skills`);
      return;
    }
    router.replace(destination);
  }, [
    loading,
    error,
    cycle,
    status,
    checkedRegistration,
    effectiveSkillId,
    competitionId,
    destination,
    router,
  ]);

  const skillsBack =
    skillIdParam
      ? `/competitions/${competitionId}/skills/${encodeURIComponent(skillIdParam)}`
      : cycle && cycle.skills.length >= 2
        ? `/competitions/${competitionId}/skills`
        : "/competitions";

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Button variant="link" className="h-auto min-h-11 px-0" asChild>
          <Link href={skillsBack}>
            ←{" "}
            {skillIdParam
              ? "Back to skill area"
              : cycle && cycle.skills.length >= 2
                ? "Back to skill areas"
                : "Back to competitions"}
          </Link>
        </Button>

        {loading || !error ? (
          <p className="mt-8 text-sm text-muted-foreground" role="status">
            Continuing to registration…
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
