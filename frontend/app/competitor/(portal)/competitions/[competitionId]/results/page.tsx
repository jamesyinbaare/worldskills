"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  fetchMyResults,
  type CompetitorResultsOut,
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

export default function CompetitorResultsPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [data, setData] = useState<CompetitorResultsOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const out = await fetchMyResults(competitionId);
        if (!cancelled) setData(out);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load your results",
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
  }, [competitionId]);

  const embargoed =
    data &&
    (data.state === "EMBARGOED" ||
      data.state === "PREPARED" ||
      data.status === "EMBARGOED" ||
      (!data.result && data.state !== "RELEASED"));

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="My results"
        description="Your outcome appears here only after results are released for this competition."
      />

      <ApiErrorAlert error={error} />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : null}

      {data ? (
        <Card data-testid="my-results">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
              Results
              <StatusBadge status={data.state} />
            </CardTitle>
            <CardDescription>
              Competition <span className="font-mono">{competitionId}</span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            {embargoed || !data.result ? (
              <Alert data-testid="my-results-embargo">
                <AlertTitle>Not released yet</AlertTitle>
                <AlertDescription>
                  Results for this competition are still under embargo. Outcomes are
                  not shown until publication is released.
                </AlertDescription>
              </Alert>
            ) : (
              <dl className="grid gap-3 text-sm" data-testid="my-results-body">
                <div>
                  <dt className="text-muted-foreground">Outcome</dt>
                  <dd>
                    <StatusBadge status={data.result.outcome} />
                  </dd>
                </div>
                {data.result.score != null ? (
                  <div>
                    <dt className="text-muted-foreground">Score</dt>
                    <dd>{data.result.score}</dd>
                  </div>
                ) : null}
                {data.result.rank != null ? (
                  <div>
                    <dt className="text-muted-foreground">Rank</dt>
                    <dd>{data.result.rank}</dd>
                  </div>
                ) : null}
                {data.certificate ? (
                  <div>
                    <dt className="text-muted-foreground">Certificate</dt>
                    <dd
                      className="font-mono text-xs break-all"
                      data-testid="my-results-certificate"
                    >
                      {data.certificate}
                    </dd>
                  </div>
                ) : null}
              </dl>
            )}
          </CardContent>
        </Card>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link href="/competitor" className="underline underline-offset-2">
          Back to competitor portal
        </Link>
      </p>
    </PageShell>
  );
}
