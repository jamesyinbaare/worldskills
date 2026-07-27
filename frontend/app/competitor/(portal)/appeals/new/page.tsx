"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  getMyStages,
  listMyRegistrations,
  lodgeAppeal,
  type AppealOut,
  type MyRegistrationOut,
  type MyStagesOut,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

function registrationLabel(row: MyRegistrationOut): string {
  return `${row.competitionName} · ${row.skillName}`;
}

function LodgeAppealPageInner() {
  const searchParams = useSearchParams();
  const competitionFromQuery = searchParams.get("competitionId") || "";
  const stageFromQuery = searchParams.get("stageId") || "";

  const [registrations, setRegistrations] = useState<MyRegistrationOut[]>([]);
  const [regsLoading, setRegsLoading] = useState(true);
  const [regsError, setRegsError] = useState<ApiError | null>(null);

  const [competitionId, setCompetitionId] = useState("");
  const [pathway, setPathway] = useState<MyStagesOut | null>(null);
  const [stagesLoading, setStagesLoading] = useState(false);
  const [stagesError, setStagesError] = useState<ApiError | null>(null);

  const [stageId, setStageId] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<AppealOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setRegsLoading(true);
      setRegsError(null);
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        setRegistrations(rows);
        const ids = new Set(rows.map((r) => r.competitionId));
        if (competitionFromQuery && ids.has(competitionFromQuery)) {
          setCompetitionId(competitionFromQuery);
        } else if (rows.length === 1) {
          setCompetitionId(rows[0].competitionId);
        }
      } catch (err) {
        if (!cancelled) {
          setRegistrations([]);
          setRegsError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load your competitions",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      } finally {
        if (!cancelled) setRegsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionFromQuery]);

  useEffect(() => {
    if (!competitionId) {
      setPathway(null);
      setStageId("");
      setStagesError(null);
      setStagesLoading(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      setStagesLoading(true);
      setStagesError(null);
      setPathway(null);
      setStageId("");
      try {
        const data = await getMyStages(competitionId);
        if (cancelled) return;
        setPathway(data);
        const stageIds = new Set(data.stages.map((s) => s.stageId));
        if (stageFromQuery && stageIds.has(stageFromQuery)) {
          setStageId(stageFromQuery);
        } else if (data.stages.length === 1) {
          setStageId(data.stages[0].stageId);
        }
      } catch (err) {
        if (!cancelled) {
          setPathway(null);
          setStagesError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load stages for this competition",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      } finally {
        if (!cancelled) setStagesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, stageFromQuery]);

  const stageOptions = useMemo(
    () =>
      (pathway?.stages ?? [])
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((stage) => ({
          value: stage.stageId,
          label: `${stage.order}. ${stage.name}`,
        })),
    [pathway],
  );

  const selectedRegistration = useMemo(
    () => registrations.find((r) => r.competitionId === competitionId) ?? null,
    [registrations, competitionId],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const competitorId =
      pathway?.competitorId || selectedRegistration?.competitorId;
    if (!competitionId || !competitorId || !stageId.trim()) return;
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const out = await lodgeAppeal(competitionId, {
        competitorId,
        stageId: stageId.trim(),
        reason: reason.trim(),
      });
      setResult(out);
    } catch (err) {
      setResult(null);
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not lodge appeal",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Lodge an appeal"
        description="Choose one of your registered competitions, then the stage you are appealing."
      />

      <ApiErrorAlert error={regsError} />
      <ApiErrorAlert error={stagesError} />
      <ApiErrorAlert error={error} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Appeal details</CardTitle>
          <CardDescription>
            Competitor ID is taken from your signed-in registration.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {regsLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : registrations.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              You have no competition registrations to appeal yet.
            </p>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="competitionId">Competition</Label>
                <Select
                  value={competitionId || undefined}
                  onValueChange={(value) => {
                    setCompetitionId(value);
                    setResult(null);
                    setError(null);
                    setFieldErrors({});
                  }}
                >
                  <SelectTrigger
                    id="competitionId"
                    className="min-h-11 w-full"
                    data-testid="appeal-competition-id"
                  >
                    <SelectValue placeholder="Select a competition" />
                  </SelectTrigger>
                  <SelectContent>
                    {registrations.map((row) => (
                      <SelectItem
                        key={`${row.competitionId}-${row.competitorId}`}
                        value={row.competitionId}
                      >
                        {registrationLabel(row)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldMessage message={fieldErrors.competitionId} />
              </div>

              <div className="space-y-2">
                <Label htmlFor="stageId">Stage</Label>
                <Select
                  value={stageId || undefined}
                  onValueChange={setStageId}
                  disabled={!competitionId || stagesLoading}
                >
                  <SelectTrigger
                    id="stageId"
                    className="min-h-11 w-full"
                    data-testid="appeal-stage-id"
                  >
                    <SelectValue
                      placeholder={
                        !competitionId
                          ? "Select a competition first"
                          : stagesLoading
                            ? "Loading stages…"
                            : "Select a stage"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {stageOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldMessage message={fieldErrors.stageId} />
                {competitionId &&
                !stagesLoading &&
                pathway &&
                stageOptions.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No stages are available on your pathway yet.
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <Label htmlFor="reason">Reason</Label>
                <Textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  rows={4}
                  disabled={!competitionId}
                  data-testid="appeal-reason"
                />
                <FieldMessage message={fieldErrors.reason} />
              </div>

              <Button
                type="submit"
                className="min-h-11 w-full"
                disabled={
                  pending ||
                  !competitionId ||
                  !stageId ||
                  stagesLoading ||
                  stageOptions.length === 0
                }
                data-testid="appeal-lodge"
              >
                {pending ? "Submitting…" : "Lodge appeal"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      {result ? (
        <Alert data-testid="appeal-lodged">
          <AlertTitle className="flex items-center gap-2">
            Appeal lodged <StatusBadge status={result.state} />
          </AlertTitle>
          <AlertDescription>
            Appeal ID{" "}
            <span className="font-mono text-xs" data-testid="appeal-id">
              {result.appealId}
            </span>
          </AlertDescription>
        </Alert>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link href="/competitor" className="underline underline-offset-2">
          Back to competitor portal
        </Link>
      </p>
    </PageShell>
  );
}

export default function LodgeAppealPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <LodgeAppealPageInner />
    </Suspense>
  );
}
