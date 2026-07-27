"use client";

import Link from "next/link";
import {
  FormEvent,
  Suspense,
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  ApiError,
  applyModeration,
  fetchScoringDetail,
  getPathway,
  listScoringOverview,
  resolveSubmissionTotal,
  type CriterionScoringOut,
  type ScoringDetailOut,
  type ScoringListItemOut,
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

function ScoringPageInner() {
  const { filters } = useCompetitionSkillQuery();
  const competitionId = filters.competitionId;

  const [rows, setRows] = useState<ScoringListItemOut[]>([]);
  const [stages, setStages] = useState<StageOut[]>([]);
  const [stageId, setStageId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<ScoringDetailOut | null>(null);
  const [resolveReason, setResolveReason] = useState("");
  const [selectedAssessorId, setSelectedAssessorId] = useState("");

  const [critDialog, setCritDialog] = useState(false);
  const [activeCriterion, setActiveCriterion] =
    useState<CriterionScoringOut | null>(null);
  const [critMethod, setCritMethod] = useState<
    "STANDARDISE" | "SELECT_ASSESSOR"
  >("STANDARDISE");
  const [critAssessorId, setCritAssessorId] = useState("");
  const [critReason, setCritReason] = useState("");

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

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
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const list = await listScoringOverview(competitionId, {
          skillId: filters.skillId || null,
          stageId: stageId || null,
        });
        if (!cancelled) setRows(list);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, filters.skillId, stageId, reloadKey]);

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

  async function openDetail(submissionId: string) {
    setPending(true);
    setError(null);
    try {
      const out = await fetchScoringDetail(submissionId);
      setDetail(out);
      setSelectedAssessorId(out.assessorTotals[0]?.assessorId ?? "");
      setResolveReason("");
      setDetailOpen(true);
    } catch (err) {
      captureErr(err, "Could not load scoring detail");
    } finally {
      setPending(false);
    }
  }

  async function onResolveTotal(method: "AVERAGE" | "SELECT_ASSESSOR") {
    if (!detail) return;
    if (method === "SELECT_ASSESSOR" && !selectedAssessorId) return;
    if (method === "SELECT_ASSESSOR" && !resolveReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await resolveSubmissionTotal(detail.submissionId, {
        method,
        assessorId:
          method === "SELECT_ASSESSOR" ? selectedAssessorId : null,
        reason: resolveReason.trim() || null,
      });
      setStatusMessage(
        `Resolved total to ${out.total} via ${out.method}.`,
      );
      const refreshed = await fetchScoringDetail(detail.submissionId);
      setDetail(refreshed);
      refresh();
    } catch (err) {
      captureErr(err, "Could not resolve total");
    } finally {
      setPending(false);
    }
  }

  function openCriterion(c: CriterionScoringOut) {
    setActiveCriterion(c);
    setCritMethod("STANDARDISE");
    setCritAssessorId(c.marks[0]?.assessorId ?? "");
    setCritReason("");
    setCritDialog(true);
  }

  async function onApplyCriterion(e: FormEvent) {
    e.preventDefault();
    if (!detail || !activeCriterion) return;
    if (critMethod === "SELECT_ASSESSOR" && !critReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await applyModeration(detail.submissionId, {
        criterionId: activeCriterion.criterionId,
        method: critMethod,
        assessorId:
          critMethod === "SELECT_ASSESSOR" ? critAssessorId : null,
        reason: critReason.trim() || null,
      });
      setCritDialog(false);
      setStatusMessage(
        `Criterion ${activeCriterion.name} resolved to ${out.standardisedValue}. Total ${out.total}.`,
      );
      const refreshed = await fetchScoringDetail(detail.submissionId);
      setDetail(refreshed);
      refresh();
    } catch (err) {
      captureErr(err, "Could not resolve criterion");
    } finally {
      setPending(false);
    }
  }

  const resultsHref =
    competitionId &&
    `/admin/results?competitionId=${encodeURIComponent(competitionId)}${
      filters.skillId
        ? `&skillId=${encodeURIComponent(filters.skillId)}`
        : ""
    }`;

  return (
    <PageShell
      width="wide"
      className="max-w-6xl space-y-5 px-0 py-0 sm:px-0 sm:py-0"
    >
      <div className="admin-panel overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Scoring"
          description="View expert marks per skill and exercise. Resolve disagreements by averaging or picking one assessor, then release from Results."
          actions={
            resultsHref ? (
              <Button asChild variant="outline" className="min-h-11 rounded-2xl">
                <Link href={resultsHref}>Go to Results</Link>
              </Button>
            ) : null
          }
        />
      </div>

      <RunCompetitionFilterBar searchPlaceholder="Filter by competition…" />

      {competitionId && filters.skillId ? (
        <div className="space-y-2">
          <Label htmlFor="scoring-stage">Stage / exercise</Label>
          <Select
            value={stageId || "__all__"}
            onValueChange={(v) => setStageId(v === "__all__" ? "" : v)}
          >
            <SelectTrigger
              id="scoring-stage"
              className="min-h-11 max-w-md rounded-2xl"
            >
              <SelectValue placeholder="All stages" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All stages</SelectItem>
              {stages.map((s) => (
                <SelectItem key={s.stageId} value={s.stageId}>
                  Stage {s.order} · {s.type}
                  {s.exerciseStatus ? ` · ${s.exerciseStatus}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
          Select a competition to view scored submissions.
        </p>
      ) : loading ? (
        <Skeleton className="h-48 w-full rounded-2xl" />
      ) : (
        <div className="overflow-hidden rounded-[1.25rem] bg-card shadow-sm ring-1 ring-foreground/5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Submission</TableHead>
                <TableHead>Skill / Stage</TableHead>
                <TableHead>Assessors</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-muted-foreground"
                  >
                    <div className="mx-auto max-w-md space-y-2">
                      <p>
                        No accepted or late submissions for this filter. Scores
                        appear here after competitors submit and experts mark.
                      </p>
                      <p className="text-xs">
                        Saving a skill pathway used to recreate stages and wipe
                        submissions — pathway edits now update stages in place.
                        If marks vanished after an earlier pathway save, the
                        competitor must re-submit and experts must re-score.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.submissionId}>
                    <TableCell>
                      <div className="font-medium">
                        {row.anonCode || row.competitorName || "—"}
                      </div>
                      {!row.blindMode && row.competitorRef ? (
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.competitorRef}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <div>{row.skillName || "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.exerciseTitle || row.stageName || "—"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {row.assessorCount} ·{" "}
                        {row.assessorTotals
                          .map((a) => a.total)
                          .join(" / ") || "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.submissionTotal ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <StatusBadge status={row.state} />
                        {row.disagreement ? (
                          <Badge variant="secondary">Disagreement</Badge>
                        ) : null}
                        {row.resultsReleased ? (
                          <Badge variant="outline">Released</Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="rounded-xl"
                        disabled={pending}
                        onClick={() => void openDetail(row.submissionId)}
                      >
                        Review
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {detail?.anonCode || "Submission scoring"}
            </DialogTitle>
            <DialogDescription>
              Compare assessor totals, then average or pick one. Optionally
              resolve individual criteria.
            </DialogDescription>
          </DialogHeader>
          {detail ? (
            <div className="space-y-5">
              <div className="rounded-2xl bg-muted/50 p-4 text-sm">
                <p>
                  Current total:{" "}
                  <strong className="tabular-nums">
                    {detail.submissionTotal ?? "—"}
                  </strong>
                </p>
                <ul className="mt-2 space-y-1">
                  {detail.assessorTotals.map((a) => (
                    <li key={a.assessorId}>
                      {a.assessorName || a.assessorEmail || a.assessorId}:{" "}
                      <span className="tabular-nums font-medium">
                        {a.total}
                      </span>{" "}
                      ({a.markCount} marks)
                    </li>
                  ))}
                </ul>
              </div>

              <div className="space-y-3 rounded-2xl border border-border/70 p-4">
                <p className="text-sm font-semibold">Resolve submission total</p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    className="rounded-2xl"
                    disabled={pending || detail.assessorTotals.length < 1}
                    onClick={() => void onResolveTotal("AVERAGE")}
                  >
                    Average totals
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Use assessor</Label>
                    <Select
                      value={selectedAssessorId || undefined}
                      onValueChange={setSelectedAssessorId}
                    >
                      <SelectTrigger className="min-h-11 rounded-2xl">
                        <SelectValue placeholder="Select assessor" />
                      </SelectTrigger>
                      <SelectContent>
                        {detail.assessorTotals.map((a) => (
                          <SelectItem key={a.assessorId} value={a.assessorId}>
                            {a.assessorName || a.assessorEmail || a.assessorId}{" "}
                            ({a.total})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="resolve-reason">Reason</Label>
                    <Input
                      id="resolve-reason"
                      className="min-h-11 rounded-2xl"
                      value={resolveReason}
                      onChange={(e) => setResolveReason(e.target.value)}
                      placeholder="Required when picking one"
                    />
                    {fieldErrors.reason ? (
                      <p className="text-sm text-destructive">
                        {fieldErrors.reason}
                      </p>
                    ) : null}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-2xl"
                  disabled={pending || !selectedAssessorId}
                  onClick={() => void onResolveTotal("SELECT_ASSESSOR")}
                >
                  Use selected assessor
                </Button>
              </div>

              <div className="space-y-3">
                <p className="text-sm font-semibold">Criteria</p>
                {detail.criteria.map((c) => (
                  <div
                    key={c.criterionId}
                    className="rounded-2xl border border-border/70 p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="font-medium">{c.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {c.type}
                          {c.max != null ? ` · max ${c.max}` : ""}
                          {c.standardisedValue != null
                            ? ` · standardised ${c.standardisedValue}`
                            : ""}
                        </p>
                        <ul className="mt-1 text-muted-foreground">
                          {c.marks.map((m) => (
                            <li key={`${c.criterionId}-${m.assessorId}`}>
                              {m.assessorName || m.assessorId}: {m.raw ?? "—"}
                            </li>
                          ))}
                        </ul>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="rounded-xl"
                        disabled={pending || c.marks.length === 0}
                        onClick={() => openCriterion(c)}
                      >
                        Resolve
                      </Button>
                    </div>
                    {c.disagreement ? (
                      <Badge className="mt-2" variant="secondary">
                        Disagreement
                      </Badge>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={critDialog} onOpenChange={setCritDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Resolve {activeCriterion?.name || "criterion"}
            </DialogTitle>
            <DialogDescription>
              Average / median via standardise, or pick one assessor’s mark.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onApplyCriterion} className="space-y-4">
            <div className="space-y-2">
              <Label>Method</Label>
              <Select
                value={critMethod}
                onValueChange={(v) =>
                  setCritMethod(v as "STANDARDISE" | "SELECT_ASSESSOR")
                }
              >
                <SelectTrigger className="min-h-11 rounded-2xl">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="STANDARDISE">
                    Standardise (mean / median)
                  </SelectItem>
                  <SelectItem value="SELECT_ASSESSOR">
                    Use one assessor’s mark
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            {critMethod === "SELECT_ASSESSOR" ? (
              <>
                <div className="space-y-2">
                  <Label>Assessor</Label>
                  <Select
                    value={critAssessorId || undefined}
                    onValueChange={setCritAssessorId}
                  >
                    <SelectTrigger className="min-h-11 rounded-2xl">
                      <SelectValue placeholder="Select assessor" />
                    </SelectTrigger>
                    <SelectContent>
                      {(activeCriterion?.marks || []).map((m) => (
                        <SelectItem key={m.assessorId} value={m.assessorId}>
                          {m.assessorName || m.assessorId}: {m.raw ?? "—"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="crit-reason">Reason</Label>
                  <Textarea
                    id="crit-reason"
                    value={critReason}
                    onChange={(e) => setCritReason(e.target.value)}
                    rows={2}
                    required
                  />
                </div>
              </>
            ) : null}
            <DialogFooter>
              <Button type="submit" disabled={pending}>
                Apply
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

export default function AdminScoringHubPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <ScoringPageInner />
    </Suspense>
  );
}
