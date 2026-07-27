"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  fetchPublicCompetitorProfile,
  type PublicCompetitorProfileOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function PublicCompetitorProfilePage() {
  const params = useParams<{ competitorKey: string }>();
  const competitorKey = params.competitorKey;

  const [profile, setProfile] = useState<PublicCompetitorProfileOut | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const out = await fetchPublicCompetitorProfile(competitorKey);
        if (!cancelled) setProfile(out);
      } catch (err) {
        if (!cancelled) {
          setProfile(null);
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load profile",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [competitorKey]);

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Competitor profile"
        description="Only privacy-allowlisted fields from the API are shown."
      />

      <ApiErrorAlert error={error} />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : null}

      {!loading && !profile && error ? (
        <Alert data-testid="profile-unavailable">
          <AlertTitle>Profile not available</AlertTitle>
          <AlertDescription>
            This competitor is not publicly listed, or the reference was not
            found. No private details are shown.
          </AlertDescription>
        </Alert>
      ) : null}

      {profile ? (
        <Card data-testid="public-profile">
          <CardHeader>
            <CardTitle className="text-lg">
              {profile.displayName ?? profile.competitorRef ?? profile.competitorId}
            </CardTitle>
            <CardDescription>
              <span className="font-mono text-xs">{profile.competitorId}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm">
              {profile.skill ? (
                <div>
                  <dt className="text-muted-foreground">Skill</dt>
                  <dd>{profile.skill}</dd>
                </div>
              ) : null}
              {profile.zone ? (
                <div>
                  <dt className="text-muted-foreground">Zone</dt>
                  <dd>{profile.zone}</dd>
                </div>
              ) : null}
              {profile.institution ? (
                <div>
                  <dt className="text-muted-foreground">Institution</dt>
                  <dd>{profile.institution}</dd>
                </div>
              ) : null}
              {profile.stageStatus ? (
                <div>
                  <dt className="text-muted-foreground">Stage status</dt>
                  <dd>
                    <StatusBadge status={profile.stageStatus} />
                  </dd>
                </div>
              ) : null}
              {profile.photo ? (
                <div>
                  <dt className="text-muted-foreground">Photo</dt>
                  <dd className="break-all font-mono text-xs">{profile.photo}</dd>
                </div>
              ) : null}
            </dl>
          </CardContent>
        </Card>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link href="/" className="underline underline-offset-2">
          Back to home
        </Link>
      </p>
    </PageShell>
  );
}
