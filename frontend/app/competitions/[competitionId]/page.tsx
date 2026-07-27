"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, getPublicCompetition } from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function CompetitionRouterPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const router = useRouter();
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getPublicCompetition(competitionId);
        if (cancelled) return;
        if (data.skills.length >= 2) {
          router.replace(`/competitions/${competitionId}/skills`);
        } else {
          const sole = data.skills[0]?.skillId;
          const qs = sole ? `?skillId=${encodeURIComponent(sole)}` : "";
          router.replace(`/competitions/${competitionId}/enter${qs}`);
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setError(err);
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
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, router]);

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-12 sm:px-6 sm:py-16">
        <Button variant="link" className="h-auto min-h-11 px-0" asChild>
          <Link href="/competitions">← Back to competitions</Link>
        </Button>
        {!error ? (
          <p className="text-sm text-muted-foreground" role="status">
            Opening competition…
          </p>
        ) : null}
        <ApiErrorAlert error={error} title="Competition unavailable" />
        {error ? (
          <Alert variant="destructive">
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
