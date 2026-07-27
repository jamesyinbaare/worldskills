"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  analyseModeration,
  applyModeration,
  fetchScoringDetail,
  resolveSubmissionTotal,
  type ModerationAnalyseOut,
  type ModerationApplyOut,
  type ModerationFlagOut,
  type ScoringDetailOut,
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
import { Textarea } from "@/components/ui/textarea";

type ApplyMethod = "STANDARDISE" | "MANUAL" | "SELECT_ASSESSOR";

export default function ExpertModerationPage() {
  const params = useParams<{ submissionId: string }>();
  const submissionId = params.submissionId;

  const [detail, setDetail] = useState<ScoringDetailOut | null>(null);
  const [analyse, setAnalyse] = useState<ModerationAnalyseOut | null>(null);
  const [lastApply, setLastApply] = useState<ModerationApplyOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [activeFlag, setActiveFlag] = useState<ModerationFlagOut | null>(null);
  const [method, setMethod] = useState<ApplyMethod>("STANDARDISE");
  const [manualValue, setManualValue] = useState("");
  const [reason, setReason] = useState("");
  const [selectAssessorId, setSelectAssessorId] = useState("");

  const [resolveReason, setResolveReason] = useState("");
  const [resolveAssessorId, setResolveAssessorId] = useState("");

  async function loadDetail() {
    try {
      const out = await fetchScoringDetail(submissionId);
      setDetail(out);
      setResolveAssessorId(out.assessorTotals[0]?.assessorId ?? "");
    } catch {
      // Chief may still analyse without detail if capability differs — ignore soft fail
    }
  }

  useEffect(() => {
    void loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submissionId]);

  async function onAnalyse() {
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await analyseModeration(submissionId);
      setAnalyse(out);
      const flagged = out.flags.filter((f) => f.flagged).length;
      setStatusMessage(
        `Analysis complete — tolerance ${out.tolerance}; ${flagged} criterion(s) flagged.`,
      );
      await loadDetail();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not analyse moderation",
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

  function openApply(flag: ModerationFlagOut, nextMethod: ApplyMethod) {
    setError(null);
    setFieldErrors({});
    setActiveFlag(flag);
    setMethod(nextMethod);
    setManualValue(
      flag.standardisedValue != null ? String(flag.standardisedValue) : "",
    );
    setReason("");
    setSelectAssessorId(detail?.assessorTotals[0]?.assessorId ?? "");
    setConfirmOpen(true);
  }

  async function onConfirmApply() {
    if (!activeFlag) return;
    if (method === "MANUAL" && !reason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    if (method === "MANUAL" && manualValue.trim() === "") {
      setFieldErrors({ value: "Manual value is required" });
      return;
    }
    if (method === "SELECT_ASSESSOR" && !reason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    if (method === "SELECT_ASSESSOR" && !selectAssessorId) {
      setFieldErrors({ assessorId: "Assessor is required" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await applyModeration(submissionId, {
        criterionId: activeFlag.criterionId,
        method,
        value: method === "MANUAL" ? Number(manualValue) : null,
        assessorId: method === "SELECT_ASSESSOR" ? selectAssessorId : null,
        reason: reason.trim() || null,
      });
      setLastApply(out);
      setConfirmOpen(false);
      setStatusMessage(
        `Applied ${out.method} on ${out.criterionId} → standardised ${out.standardisedValue}; total ${out.total}.`,
      );
      const refreshed = await analyseModeration(submissionId);
      setAnalyse(refreshed);
      await loadDetail();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
        if (err.code === "SEGREGATION_VIOLATION") {
          setConfirmOpen(false);
        }
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not apply moderation",
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

  async function onResolveTotal(next: "AVERAGE" | "SELECT_ASSESSOR") {
    if (next === "SELECT_ASSESSOR" && !resolveReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await resolveSubmissionTotal(submissionId, {
        method: next,
        assessorId: next === "SELECT_ASSESSOR" ? resolveAssessorId : null,
        reason: resolveReason.trim() || null,
      });
      setStatusMessage(`Submission total resolved to ${out.total} via ${out.method}.`);
      await loadDetail();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not resolve total",
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
        title="Score moderation"
        description="Compare assessor totals, resolve disagreements, and standardise criterion marks. Raw marks stay on record."
        backHref={`/expert/submissions/${submissionId}`}
        backLabel="Back to scoring"
      />

      {statusMessage ? (
        <Alert data-testid="moderation-status-message">
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert error={error} />

      {detail ? (
        <Card data-testid="moderation-scoring-overview">
          <CardHeader>
            <CardTitle className="text-lg">
              {detail.anonCode || "Submission"}
            </CardTitle>
            <CardDescription>
              Current total{" "}
              <strong className="tabular-nums">
                {detail.submissionTotal ?? "—"}
              </strong>
              {detail.disagreement ? " · disagreement detected" : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-1 text-sm">
              {detail.assessorTotals.map((a) => (
                <li key={a.assessorId}>
                  {a.assessorName || a.assessorEmail || a.assessorId}:{" "}
                  <span className="font-medium tabular-nums">{a.total}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                className="min-h-11 rounded-2xl"
                disabled={pending || detail.assessorTotals.length < 1}
                onClick={() => void onResolveTotal("AVERAGE")}
                data-testid="moderation-resolve-average"
              >
                Average totals
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Use assessor</Label>
                <Select
                  value={resolveAssessorId || undefined}
                  onValueChange={setResolveAssessorId}
                >
                  <SelectTrigger className="min-h-11 rounded-2xl">
                    <SelectValue placeholder="Select assessor" />
                  </SelectTrigger>
                  <SelectContent>
                    {detail.assessorTotals.map((a) => (
                      <SelectItem key={a.assessorId} value={a.assessorId}>
                        {a.assessorName || a.assessorEmail || a.assessorId} (
                        {a.total})
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
                <FieldMessage message={fieldErrors.reason} />
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 rounded-2xl"
              disabled={pending || !resolveAssessorId}
              onClick={() => void onResolveTotal("SELECT_ASSESSOR")}
              data-testid="moderation-resolve-select"
            >
              Use selected assessor
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Button
        type="button"
        className="min-h-11 w-full"
        disabled={pending}
        onClick={() => void onAnalyse()}
        data-testid="moderation-analyse"
      >
        {pending ? "Working…" : "Analyse criterion spread"}
      </Button>

      {analyse ? (
        <Card data-testid="moderation-flags">
          <CardHeader>
            <CardTitle className="text-lg">Criteria</CardTitle>
            <CardDescription>
              Tolerance: {analyse.tolerance}. Flagged criteria exceed inter-judge
              spread.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-4">
              {analyse.flags.map((flag) => (
                <li
                  key={flag.criterionId}
                  className="rounded-md border border-border p-4"
                  data-testid="moderation-flag"
                  data-criterion={flag.criterionId}
                  data-flagged={flag.flagged ? "true" : "false"}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono font-medium">
                      {flag.criterionId}
                    </span>
                    <StatusBadge
                      status={flag.flagged ? "pending" : "approved"}
                      label={flag.flagged ? "Flagged" : "Within tolerance"}
                    />
                    <StatusBadge status={flag.state} />
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Raw marks: {flag.rawMarks.join(", ") || "—"}
                    {flag.spread != null ? ` · Spread: ${flag.spread}` : ""}
                  </p>
                  {flag.standardisedValue != null ? (
                    <p
                      className="mt-1 text-sm"
                      data-testid="moderation-standardised"
                    >
                      Standardised value: {flag.standardisedValue}
                      {flag.method ? ` (${flag.method})` : ""}
                    </p>
                  ) : null}
                  {flag.flagged ? (
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                      <Button
                        type="button"
                        className="min-h-11"
                        disabled={pending}
                        onClick={() => openApply(flag, "STANDARDISE")}
                        data-testid="moderation-standardise"
                      >
                        Standardise
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11"
                        disabled={pending}
                        onClick={() => openApply(flag, "MANUAL")}
                        data-testid="moderation-manual"
                      >
                        Manual adjust
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11"
                        disabled={pending}
                        onClick={() => openApply(flag, "SELECT_ASSESSOR")}
                        data-testid="moderation-select-assessor"
                      >
                        Use one assessor
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {lastApply ? (
        <Alert data-testid="moderation-apply-result">
          <AlertTitle>Last adjustment</AlertTitle>
          <AlertDescription>
            <p>
              {lastApply.criterionId}: standardised{" "}
              <strong>{lastApply.standardisedValue}</strong> via {lastApply.method}
            </p>
            <p className="mt-1">
              Updated total:{" "}
              <strong data-testid="moderation-total">{lastApply.total}</strong>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Raw marks unchanged: {lastApply.rawMarks.join(", ")}
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent data-testid="moderation-confirm">
          <DialogHeader>
            <DialogTitle>
              {method === "STANDARDISE"
                ? "Apply standardisation"
                : method === "SELECT_ASSESSOR"
                  ? "Use one assessor’s mark"
                  : "Manual adjustment"}
            </DialogTitle>
            <DialogDescription>
              Criterion {activeFlag?.criterionId}. Raw marks stay on record;
              only the standardised value changes.
            </DialogDescription>
          </DialogHeader>
          {method === "MANUAL" ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="manualValue">Standardised value</Label>
                <Input
                  id="manualValue"
                  type="number"
                  className="min-h-11"
                  value={manualValue}
                  onChange={(e) => setManualValue(e.target.value)}
                  data-testid="moderation-manual-value"
                  aria-invalid={Boolean(fieldErrors.value)}
                />
                <FieldMessage message={fieldErrors.value} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="moderationReason">Reason (required)</Label>
                <Textarea
                  id="moderationReason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  rows={3}
                  data-testid="moderation-reason"
                  aria-invalid={Boolean(fieldErrors.reason)}
                />
                <FieldMessage message={fieldErrors.reason} />
              </div>
            </div>
          ) : method === "SELECT_ASSESSOR" ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Assessor</Label>
                <Select
                  value={selectAssessorId || undefined}
                  onValueChange={setSelectAssessorId}
                >
                  <SelectTrigger className="min-h-11 rounded-2xl">
                    <SelectValue placeholder="Select assessor" />
                  </SelectTrigger>
                  <SelectContent>
                    {(detail?.assessorTotals || []).map((a) => (
                      <SelectItem key={a.assessorId} value={a.assessorId}>
                        {a.assessorName || a.assessorEmail || a.assessorId}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldMessage message={fieldErrors.assessorId} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="selectReason">Reason (required)</Label>
                <Textarea
                  id="selectReason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  rows={3}
                />
                <FieldMessage message={fieldErrors.reason} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              The configured standardisation rule will set the moderated value.
            </p>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => setConfirmOpen(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="min-h-11"
              disabled={pending}
              onClick={() => void onConfirmApply()}
              data-testid="moderation-confirm-submit"
            >
              {pending ? "Applying…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="text-xs text-muted-foreground">
        <Link
          href={`/expert/submissions/${submissionId}`}
          className="underline underline-offset-2"
        >
          Back to scoring
        </Link>
        {" · "}
        <Link href="/expert" className="underline underline-offset-2">
          Assessor portal
        </Link>
      </p>
    </PageShell>
  );
}
