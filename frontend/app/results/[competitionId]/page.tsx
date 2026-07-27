"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  fetchPublicResults,
  type PublicResultsOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function PublicResultsBody({ competitionId }: { competitionId: string }) {
  const [data, setData] = useState<PublicResultsOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const out = await fetchPublicResults(competitionId);
        if (!cancelled) setData(out);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load public results",
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

  const released =
    data &&
    (data.state === "RELEASED" || data.status === "RELEASED") &&
    data.results.length > 0;

  return (
    <>
      <ApiErrorAlert error={error} />
      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : null}
      {data ? (
        <Card data-testid="public-results">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
              Public results
              <StatusBadge status={data.state} />
            </CardTitle>
            <CardDescription>
              {data.releasedAt
                ? `Released ${new Date(data.releasedAt).toLocaleString()}`
                : "Awaiting release"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!released ? (
              <Alert data-testid="public-results-embargo">
                <AlertTitle>Embargoed</AlertTitle>
                <AlertDescription>
                  Results are not available publicly until the embargo is
                  lifted. No outcomes are listed.
                </AlertDescription>
              </Alert>
            ) : (
              <ul className="space-y-3" data-testid="public-results-list">
                {data.results.map((r) => (
                  <li
                    key={r.resultId}
                    className="rounded-md border border-border p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs">
                        {r.refNo ?? r.competitorId}
                      </span>
                      <StatusBadge status={r.outcome} />
                    </div>
                    <p className="mt-1 text-muted-foreground">
                      {r.score != null ? `Score ${r.score}` : null}
                      {r.rank != null ? ` · Rank ${r.rank}` : null}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

export default function PublicResultsPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const router = useRouter();
  const [lookup, setLookup] = useState(competitionId || "");

  function onLookup(e: FormEvent) {
    e.preventDefault();
    const id = lookup.trim();
    if (!id) return;
    router.push(`/results/${id}`);
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Competition results"
        description="Public outcomes appear here only after the embargo is released."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Lookup cycle</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onLookup} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="cycleLookup">Competition ID</Label>
              <Input
                id="cycleLookup"
                className="min-h-11"
                value={lookup}
                onChange={(e) => setLookup(e.target.value)}
                data-testid="public-results-cycle-id"
              />
            </div>
            <Button type="submit" className="min-h-11" data-testid="public-results-go">
              View
            </Button>
          </form>
        </CardContent>
      </Card>

      {competitionId ? <PublicResultsBody competitionId={competitionId} /> : null}

      <p className="text-xs text-muted-foreground">
        <Link href="/" className="underline underline-offset-2">
          Back to home
        </Link>
      </p>
    </PageShell>
  );
}
