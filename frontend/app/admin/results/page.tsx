"use client";

import Link from "next/link";
import { FormEvent, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  AdminResultItem,
  ApiError,
  correctResult,
  getPathway,
  getResultsConfig,
  listAdminResults,
  prepareResults,
  putResultsConfig,
  releaseResults,
  type ResultsConfigOut,
  type StageOut,
} from "@/lib/api";
import { ApiErrorAlert, fieldErrorMap } from "@/components/forms/ApiErrorAlert";
import {
  RunCompetitionFilterBar,
  useCompetitionSkillQuery,
} from "@/components/admin/run/useCompetitionSkillQuery";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

const AUDIENCE_OPTIONS = [
  { value: "PUBLIC", label: "Public" },
  { value: "COMPETITOR", label: "Competitors" },
  { value: "INSTITUTION", label: "Institutions" },
] as const;

function toLocalInputValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(local: string): string {
  const d = new Date(local);
  return d.toISOString();
}

function ResultsPageInner() {
  const { filters } = useCompetitionSkillQuery();
  const competitionId = filters.competitionId;

  const [rows, setRows] = useState<AdminResultItem[]>([]);
  const [config, setConfig] = useState<ResultsConfigOut | null>(null);
  const [stages, setStages] = useState<StageOut[]>([]);
  const [stageId, setStageId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [releaseAtLocal, setReleaseAtLocal] = useState("");
  const [audience, setAudience] = useState<string[]>(["PUBLIC", "COMPETITOR"]);
  const [neutralStatus, setNeutralStatus] = useState("IN_PROGRESS");
  const [defaultOutcome, setDefaultOutcome] = useState("FINALIST");

  const [correctOpen, setCorrectOpen] = useState(false);
  const [correctResultId, setCorrectResultId] = useState("");
  const [outcome, setOutcome] = useState("");
  const [reason, setReason] = useState("");

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  const configIncomplete =
    error?.code === "CONFIG_INCOMPLETE" ||
    (config != null && !config.configured);

  useEffect(() => {
    setStageId("");
  }, [filters.skillId, competitionId]);

  useEffect(() => {
    if (!competitionId || !filters.skillId) {
      setStages([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const pathway = await getPathway(competitionId, filters.skillId);
        if (!cancelled) setStages(pathway.stages ?? []);
      } catch {
        if (!cancelled) setStages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, filters.skillId]);

  useEffect(() => {
    if (!competitionId) {
      setRows([]);
      setConfig(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [list, cfg] = await Promise.all([
          listAdminResults(competitionId, {
            skillId: filters.skillId || null,
            q: filters.q || null,
          }),
          getResultsConfig(competitionId),
        ]);
        if (cancelled) return;
        setRows(list);
        setConfig(cfg);
        setReleaseAtLocal(toLocalInputValue(cfg.releaseAt));
        setAudience(cfg.audience?.length ? cfg.audience : ["PUBLIC", "COMPETITOR"]);
        setNeutralStatus(cfg.neutralStatus || "IN_PROGRESS");
        setDefaultOutcome(cfg.defaultOutcome || "FINALIST");
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, filters.skillId, filters.q, reloadKey]);

  function captureErr(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setError(err);
      setFieldErrors(fieldErrorMap(err.fields));
    } else {
      setError(
        new ApiError(0, {
          error: {
            code: "HTTP_ERROR",
            message: fallback,
            fields: [],
            traceId: "",
          },
        }),
      );
    }
  }

  async function onSaveConfig(e: FormEvent) {
    e.preventDefault();
    if (!competitionId || !releaseAtLocal) return;
    setPending(true);
    setError(null);
    setFieldErrors({});
    setStatusMessage(null);
    try {
      const out = await putResultsConfig(competitionId, {
        releaseAt: fromLocalInputValue(releaseAtLocal),
        audience,
        neutralStatus,
        defaultOutcome,
        awardByRank: { "1": "GOLD", "2": "SILVER", "3": "BRONZE" },
        ensureTemplates: true,
      });
      setConfig(out);
      setStatusMessage(
        "Results release settings saved. Certificate templates were created for awards and stage outcomes.",
      );
      refresh();
    } catch (err) {
      captureErr(err, "Could not save results config");
    } finally {
      setPending(false);
    }
  }

  async function onPrepare() {
    if (!competitionId) return;
    setPending(true);
    setError(null);
    setStatusMessage(null);
    try {
      const out = await prepareResults(competitionId, {
        skillId: filters.skillId || null,
        stageId: stageId || null,
      });
      setStatusMessage(
        `Prepared ${out.entryCount} entr(y/ies). Embargo until ${new Date(out.releaseAt).toLocaleString()}.`,
      );
      refresh();
    } catch (err) {
      captureErr(err, "Could not prepare results");
    } finally {
      setPending(false);
    }
  }

  async function onRelease() {
    if (!competitionId) return;
    setPending(true);
    setError(null);
    setStatusMessage(null);
    try {
      const out = await releaseResults(competitionId, {
        manual: true,
        skillId: stageId ? null : filters.skillId || null,
        stageId: stageId || null,
      });
      setStatusMessage(
        `Released. ${out.certificateCount} certificate(s) issued.`,
      );
      refresh();
    } catch (err) {
      captureErr(err, "Could not release results");
    } finally {
      setPending(false);
    }
  }

  async function onCorrect(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const changes: Record<string, unknown> = {};
      if (outcome.trim()) changes.outcome = outcome.trim();
      const out = await correctResult(correctResultId, {
        changes,
        reason: reason.trim(),
      });
      setCorrectOpen(false);
      setStatusMessage(`Corrected result to version ${out.version}.`);
      refresh();
    } catch (err) {
      captureErr(err, "Could not correct result");
    } finally {
      setPending(false);
    }
  }

  function toggleAudience(value: string, checked: boolean) {
    setAudience((prev) =>
      checked
        ? prev.includes(value)
          ? prev
          : [...prev, value]
        : prev.filter((a) => a !== value),
    );
  }

  const scopeHint = useMemo(() => {
    if (stageId) {
      const stage = stages.find((s) => s.stageId === stageId);
      return stage
        ? `Exercise release: stage ${stage.order} (${stage.type}). Prepare uses the confirmed shortlist for this exercise; Release locks further expert score edits.`
        : "Exercise release for the selected stage.";
    }
    if (filters.skillId) {
      return "Finals awards for the selected skill (confirmed final shortlist). Prefer selecting a stage to release a specific exercise.";
    }
    if (competitionId) {
      return "Finals awards for the whole competition. Select a skill and stage to release one exercise independently.";
    }
    return null;
  }, [stageId, stages, filters.skillId, competitionId]);

  const scoringHref =
    competitionId &&
    `/admin/scoring?competitionId=${encodeURIComponent(competitionId)}${
      filters.skillId
        ? `&skillId=${encodeURIComponent(filters.skillId)}`
        : ""
    }`;

  return (
    <PageShell width="wide" className="max-w-6xl space-y-5 px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Results"
          description="Configure embargo and audience, then prepare and release results for a stage exercise or finals awards. Prepare copies confirmed shortlist totals (from resolved submission scores)."
          actions={
            <div className="flex flex-wrap gap-2">
              {scoringHref ? (
                <Button
                  asChild
                  variant="ghost"
                  className="min-h-11 rounded-2xl"
                >
                  <Link href={scoringHref}>View scores</Link>
                </Button>
              ) : null}
              <Button
                className="min-h-11 rounded-2xl"
                variant="outline"
                disabled={!competitionId || pending || configIncomplete}
                onClick={onPrepare}
              >
                Prepare
              </Button>
              <Button
                className="min-h-11 rounded-2xl"
                disabled={!competitionId || pending || configIncomplete}
                onClick={onRelease}
              >
                Release now
              </Button>
            </div>
          }
        />
      </div>

      <RunCompetitionFilterBar searchPlaceholder="Search competitor, skill, or outcome…" />

      {competitionId && filters.skillId ? (
        <div className="space-y-2">
          <Label htmlFor="results-stage">Stage / exercise</Label>
          <Select
            value={stageId || "__finals__"}
            onValueChange={(v) => setStageId(v === "__finals__" ? "" : v)}
          >
            <SelectTrigger id="results-stage" className="min-h-11 max-w-md rounded-2xl">
              <SelectValue placeholder="Finals awards (skill / competition)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__finals__">
                Finals awards only (confirmed final shortlist)
              </SelectItem>
              {stages.map((s) => (
                <SelectItem key={s.stageId} value={s.stageId}>
                  Exercise · stage {s.order} · {s.type}
                  {s.exerciseStatus ? ` · ${s.exerciseStatus}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {stageId ? (
            <p className="text-xs text-muted-foreground">
              <Link
                href={`/admin/scoring?competitionId=${encodeURIComponent(competitionId)}&skillId=${encodeURIComponent(filters.skillId)}`}
                className="underline underline-offset-2"
              >
                View scores for this exercise
              </Link>
            </p>
          ) : null}
        </div>
      ) : null}

      {scopeHint ? (
        <p className="text-xs text-muted-foreground">{scopeHint}</p>
      ) : null}

      {competitionId ? (
        <form
          onSubmit={onSaveConfig}
          className="space-y-4 rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6"
          data-testid="results-config-form"
        >
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Release settings
            </h2>
            <p className="text-sm text-muted-foreground">
              Embargo time and who can see results after release. Saving also
              creates default certificate templates.
            </p>
          </div>

          {configIncomplete ? (
            <Alert className="rounded-2xl">
              <AlertTitle>Setup required</AlertTitle>
              <AlertDescription>
                Results embargo / audience config is missing. Save settings
                below before Prepare or Release.
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="release-at">Embargo lifts at</Label>
              <Input
                id="release-at"
                type="datetime-local"
                className="min-h-11 rounded-2xl"
                value={releaseAtLocal}
                onChange={(e) => setReleaseAtLocal(e.target.value)}
                required
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="rounded-xl"
                onClick={() => setReleaseAtLocal(toLocalInputValue(new Date().toISOString()))}
              >
                Set to now
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="neutral-status">Neutral status (while embargoed)</Label>
              <Input
                id="neutral-status"
                className="min-h-11 rounded-2xl"
                value={neutralStatus}
                onChange={(e) => setNeutralStatus(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Audience after release</Label>
            <div className="flex flex-wrap gap-3">
              {AUDIENCE_OPTIONS.map((opt) => {
                const checked = audience.includes(opt.value);
                return (
                  <label
                    key={opt.value}
                    className="flex min-h-11 cursor-pointer items-center gap-2 rounded-2xl border border-border/70 px-3 text-sm"
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(v) =>
                        toggleAudience(opt.value, Boolean(v))
                      }
                    />
                    {opt.label}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="space-y-2 sm:max-w-xs">
            <Label htmlFor="default-outcome">Default award (beyond top 3)</Label>
            <Input
              id="default-outcome"
              className="min-h-11 rounded-2xl"
              value={defaultOutcome}
              onChange={(e) => setDefaultOutcome(e.target.value)}
            />
          </div>

          <Button
            type="submit"
            className="min-h-11 rounded-2xl"
            disabled={pending || audience.length === 0 || !releaseAtLocal}
          >
            {pending ? "Saving…" : config?.configured ? "Update settings" : "Save settings"}
          </Button>
        </form>
      ) : null}

      {statusMessage ? (
        <Alert>
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}
      <ApiErrorAlert error={error} />

      {!competitionId ? (
        <p className="text-sm text-muted-foreground">
          Select a competition to view result entries.
        </p>
      ) : loading ? (
        <Skeleton className="h-48 w-full rounded-2xl" />
      ) : (
        <div className="overflow-hidden rounded-[1.25rem] bg-card shadow-sm ring-1 ring-foreground/5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Competitor</TableHead>
                <TableHead>Skill</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead className="text-right">Rank</TableHead>
                <TableHead>Publication</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                    No result entries yet. Save release settings, confirm a
                    shortlist, then Prepare.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.resultId}>
                    <TableCell>
                      <div className="font-medium">
                        {row.competitorName || row.competitorRef || "—"}
                      </div>
                      {row.competitorRef ? (
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.competitorRef}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell>{row.skillName}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.stageName || "Finals"}
                    </TableCell>
                    <TableCell>{row.outcome}</TableCell>
                    <TableCell className="text-right">
                      {row.score ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {row.rank ?? "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.publicationState} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="rounded-xl"
                        onClick={() => {
                          setCorrectResultId(row.resultId);
                          setOutcome(row.outcome);
                          setReason("");
                          setCorrectOpen(true);
                        }}
                      >
                        Correct
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={correctOpen} onOpenChange={setCorrectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Correct result</DialogTitle>
            <DialogDescription>
              Creates a new version of the result entry. Reason is required.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onCorrect} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="outcome">Outcome</Label>
              <Input
                id="outcome"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reason">Reason</Label>
              <Textarea
                id="reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
                rows={3}
              />
              {fieldErrors.reason ? (
                <p className="text-sm text-destructive">{fieldErrors.reason}</p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending || !reason.trim()}>
                Save correction
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

export default function AdminResultsHubPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <ResultsPageInner />
    </Suspense>
  );
}
