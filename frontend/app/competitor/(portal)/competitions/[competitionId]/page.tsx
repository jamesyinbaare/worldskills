"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  getMyStages,
  type MyStageOut,
  type MyStagesOut,
} from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "Not set";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function windowLabel(status: string): string {
  switch (status) {
    case "open":
      return "Open";
    case "upcoming":
      return "Upcoming";
    case "closed":
      return "Closed";
    default:
      return "Window TBD";
  }
}

function stagePrimaryAction(
  competitionId: string,
  stage: MyStageOut,
): { label: string; href: string } | null {
  if (!stage.exerciseAvailable) return null;
  const state = (stage.submission.state || "").toUpperCase();
  const href = `/competitor/competitions/${competitionId}/stages/${stage.stageId}/submit`;
  if (["ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"].includes(state)) {
    return { label: "View receipt", href };
  }
  if (state === "OPEN" || state === "UPLOADED" || state === "SCANNING" || state === "QUARANTINED") {
    return { label: "Continue submission", href };
  }
  // Do not open a submission before the stage window (avoids starting timed projects early).
  if (stage.windowStatus === "upcoming") return null;
  if (stage.windowStatus === "closed" && !state) return null;
  return { label: "View exercise & submit", href };
}

function stageStatusBadge(stage: MyStageOut): { status: string; label: string } {
  const state = (stage.submission.state || "").toUpperCase();
  if (["ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"].includes(state)) {
    return { status: "submitted", label: "Submitted" };
  }
  if (state === "OPEN" || state === "UPLOADED" || state === "SCANNING") {
    return { status: "open", label: "In progress" };
  }
  if (!stage.exerciseAvailable) {
    return { status: "pending", label: "Not released" };
  }
  if (stage.windowStatus === "upcoming") {
    return { status: "pending", label: "Upcoming" };
  }
  if (stage.windowStatus === "closed") {
    return { status: "closed", label: "Closed" };
  }
  if (stage.windowStatus === "open") {
    return { status: "open", label: "Open" };
  }
  return { status: "configured", label: "Available" };
}

export default function CompetitorCompetitionPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [pathway, setPathway] = useState<MyStagesOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await getMyStages(competitionId);
        if (!cancelled) {
          setPathway(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setPathway(null);
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title={pathway?.competitionName ?? "Competition"}
        description={
          pathway
            ? `${pathway.skillName} · your stage pathway`
            : "Loading your stage pathway…"
        }
      />
      <ApiErrorAlert error={error} title="Could not load stages" />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading stages…
        </p>
      ) : null}

      {!loading && pathway && pathway.stages.length === 0 ? (
        <Card>
          <CardContent className="py-8">
            <p className="text-sm text-muted-foreground">
              No stages are configured for your skill yet. Check back later.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {pathway && pathway.stages.length > 0 ? (
        <ol
          className="relative space-y-4 border-l border-border/80 pl-6"
          data-testid="competitor-stage-pathway"
        >
          {pathway.stages.map((stage) => {
            const badge = stageStatusBadge(stage);
            const action = stagePrimaryAction(competitionId, stage);
            return (
              <li
                key={stage.stageId}
                className="relative"
                data-testid={`competitor-stage-${stage.stageId}`}
              >
                <span
                  className="absolute top-5 left-[-1.65rem] flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card text-[0.65rem] font-semibold text-muted-foreground"
                  aria-hidden
                >
                  {stage.order}
                </span>
                <Card>
                  <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
                    <div className="min-w-0 space-y-1">
                      <h2 className="text-base font-semibold leading-snug">
                        {stage.exerciseAvailable && stage.exerciseTitle
                          ? stage.exerciseTitle
                          : stage.name}
                      </h2>
                      <CardDescription>
                        Stage {stage.order}
                        {stage.type ? ` · ${stage.type}` : null}
                        {" · "}
                        {windowLabel(stage.windowStatus)}
                      </CardDescription>
                    </div>
                    <StatusBadge status={badge.status} label={badge.label} />
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <dl className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                      <div>
                        <dt className="font-medium text-foreground">
                          Available from
                        </dt>
                        <dd data-testid={`stage-opens-${stage.stageId}`}>
                          {formatWhen(stage.opensAt)}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-medium text-foreground">
                          Submission deadline
                        </dt>
                        <dd data-testid={`stage-closes-${stage.stageId}`}>
                          {formatWhen(stage.closesAt)}
                        </dd>
                      </div>
                    </dl>
                    {!stage.exerciseAvailable ? (
                      <p className="text-sm text-muted-foreground">
                        No exercise published yet — check back when the stage
                        opens.
                      </p>
                    ) : null}
                    {stage.exerciseAvailable &&
                    stage.windowStatus === "upcoming" ? (
                      <p
                        className="text-sm text-muted-foreground"
                        data-testid={`stage-upcoming-${stage.stageId}`}
                      >
                        This exercise opens{" "}
                        <span className="font-medium text-foreground">
                          {formatWhen(stage.opensAt)}
                        </span>
                        . You can view and submit once it becomes available.
                      </p>
                    ) : null}
                    {stage.exerciseAvailable &&
                    stage.windowStatus === "closed" &&
                    !stage.submission.state ? (
                      <p className="text-sm text-muted-foreground">
                        The submission window has closed
                        {stage.closesAt
                          ? ` (${formatWhen(stage.closesAt)})`
                          : ""}
                        .
                      </p>
                    ) : null}
                    {stage.submission.state ? (
                      <p className="text-sm text-muted-foreground">
                        Submission status:{" "}
                        <span className="font-medium text-foreground">
                          {stage.submission.state}
                        </span>
                        {stage.submission.receipt
                          ? ` · receipt ${stage.submission.receipt}`
                          : null}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      {action ? (
                        <Button
                          className="min-h-11"
                          asChild
                          data-testid={`stage-cta-${stage.stageId}`}
                        >
                          <Link href={action.href}>{action.label}</Link>
                        </Button>
                      ) : null}
                      <Button
                        variant="outline"
                        className="min-h-11"
                        asChild
                      >
                        <Link
                          href={`/competitor/competitions/${competitionId}/results`}
                        >
                          Results
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ol>
      ) : null}

      <p className="text-sm text-muted-foreground">
        <Link
          href="/competitor"
          className="underline underline-offset-2 hover:text-foreground"
        >
          Back to overview
        </Link>
      </p>
    </PageShell>
  );
}
