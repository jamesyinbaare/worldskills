"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  confirmShortlist,
  generateShortlist,
  type ShortlistConfirmOut,
  type ShortlistGenerateOut,
  type ShortlistRankedItem,
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

function RankedTable({
  rows,
  showZone,
}: {
  rows: ShortlistRankedItem[];
  showZone?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Rank</th>
            <th className="py-2 pr-3 font-medium">Competitor</th>
            {showZone ? (
              <th className="py-2 pr-3 font-medium">Zone</th>
            ) : null}
            <th className="py-2 pr-3 font-medium">Score</th>
            <th className="py-2 pr-3 font-medium">Outcome</th>
            <th className="py-2 font-medium">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.competitorId}
              className="border-b border-border/60"
              data-testid="shortlist-row"
              data-outcome={row.outcome}
            >
              <td className="py-2 pr-3">{row.rank}</td>
              <td className="py-2 pr-3 font-mono text-xs">
                {row.refNo ?? row.competitorId}
              </td>
              {showZone ? (
                <td className="py-2 pr-3 font-mono text-xs">{row.zoneId}</td>
              ) : null}
              <td className="py-2 pr-3">{row.score}</td>
              <td className="py-2 pr-3">
                <StatusBadge status={row.outcome} />
              </td>
              <td className="py-2 text-muted-foreground">
                {row.reason ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ShortlistPage() {
  const params = useParams<{ id: string; stageId: string }>();
  const competitionId = params.id;
  const stageId = params.stageId;

  const [preview, setPreview] = useState<ShortlistGenerateOut | null>(null);
  const [confirmed, setConfirmed] = useState<ShortlistConfirmOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  async function onGenerate() {
    setError(null);
    setConfirmed(null);
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await generateShortlist(competitionId, stageId);
      setPreview(out);
      const mode =
        out.selectionMode === "NATIONAL_POOL" ? "national pool" : "by zone";
      setStatusMessage(
        `Provisional shortlist generated (${out.state}, ${mode}). Review, then confirm to advance competitors.`,
      );
    } catch (err) {
      setPreview(null);
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not generate shortlist",
                fields: [],
                traceId: "",
              },
            }),
      );
    } finally {
      setPending(false);
    }
  }

  async function onConfirm() {
    if (!preview || confirmed) return;
    setError(null);
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await confirmShortlist(competitionId, stageId);
      setConfirmed(out);
      setStatusMessage(
        `Shortlist confirmed (${out.state}). ${out.advanced.length} advanced, ${out.waitlist.length} waitlisted.`,
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not confirm shortlist",
                fields: [],
                traceId: "",
              },
            }),
      );
    } finally {
      setPending(false);
    }
  }

  const isNational = preview?.selectionMode === "NATIONAL_POOL";
  const zones = preview?.byZone ? Object.entries(preview.byZone) : [];
  const nationalRows = preview?.national ?? [];

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title="Shortlist"
        description="Generate a provisional ranked shortlist (per zone or national pool), then confirm to advance competitors. Nothing advances until you confirm."
      />

      <p className="text-sm text-muted-foreground">
        Competition <span className="font-mono">{competitionId}</span>
        {" · "}
        Stage <span className="font-mono">{stageId}</span>
      </p>

      {statusMessage ? (
        <Alert data-testid="shortlist-status-message">
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert error={error} />

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          type="button"
          className="min-h-11"
          disabled={pending}
          onClick={() => void onGenerate()}
          data-testid="shortlist-generate"
        >
          {pending ? "Working…" : "Generate provisional shortlist"}
        </Button>
        <Button
          type="button"
          variant="accent"
          className="min-h-11"
          disabled={pending || !preview || Boolean(confirmed)}
          onClick={() => void onConfirm()}
          data-testid="shortlist-confirm"
        >
          Confirm shortlist
        </Button>
      </div>

      {preview ? (
        <Card data-testid="shortlist-preview">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
              Preview
              <StatusBadge status={preview.state} />
              <StatusBadge
                status={isNational ? "national" : "per-zone"}
                label={isNational ? "National pool" : "Per zone"}
              />
              {preview.isFinalStage ? (
                <StatusBadge status="final" label="Final stage" />
              ) : null}
            </CardTitle>
            <CardDescription>
              Shortlist{" "}
              <span className="font-mono text-xs">{preview.shortlistId}</span>
              {" · "}
              Generated {new Date(preview.generatedAt).toLocaleString()}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {isNational ? (
              <div data-testid="shortlist-national">
                <h3 className="mb-2 text-sm font-semibold">National pool</h3>
                <RankedTable rows={nationalRows} showZone />
              </div>
            ) : (
              zones.map(([zoneId, rows]) => (
                <div key={zoneId} data-testid="shortlist-zone">
                  <h3 className="mb-2 text-sm font-semibold">
                    Zone <span className="font-mono">{zoneId}</span>
                  </h3>
                  <RankedTable rows={rows} />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ) : null}

      {confirmed ? (
        <Card data-testid="shortlist-confirmed">
          <CardHeader>
            <CardTitle className="text-lg">Confirmation result</CardTitle>
            <CardDescription>
              State <StatusBadge status={confirmed.state} />
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <p className="font-medium">Advanced ({confirmed.advanced.length})</p>
              <ul className="mt-1 list-disc pl-5 font-mono text-xs">
                {confirmed.advanced.map((id) => (
                  <li key={id}>{id}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium">Waitlist ({confirmed.waitlist.length})</p>
              <ul className="mt-1 list-disc pl-5 font-mono text-xs">
                {confirmed.waitlist.map((id) => (
                  <li key={id}>{id}</li>
                ))}
              </ul>
            </div>
            {confirmed.finalists && confirmed.finalists.length > 0 ? (
              <div data-testid="shortlist-finalists">
                <p className="font-medium">Finalists</p>
                <ul className="mt-1 list-disc pl-5 text-xs">
                  {confirmed.finalists.map((f) => (
                    <li key={f.competitorId}>
                      {f.refNo ?? f.competitorId} — rank {f.rank}, score {f.score}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link
          href={`/admin/competitions/${competitionId}`}
          className="underline underline-offset-2"
        >
          Back to cycle workspace
        </Link>
      </p>
    </PageShell>
  );
}
