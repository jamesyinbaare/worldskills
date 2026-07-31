"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  SUBMISSION_RESUMABLE_THRESHOLD_BYTES,
  downloadExercisePack,
  expireSubmissionTimer,
  finaliseSubmission,
  getExercise,
  getMyStages,
  openSubmission,
  reopenSubmission,
  triggerBrowserDownload,
  uploadArtefact,
  uploadArtefactResumable,
  type ArtefactUploadOut,
  type ExerciseOut,
  type FinaliseOut,
  type MyStageOut,
  type SubmissionOut,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type UploadRecord = {
  deliverableCode: string;
  filename: string;
  artefactId: string;
  scan: string;
  quarantined: boolean;
  complete: boolean;
  progress?: { received: number; total: number };
};

function formatDeadline(iso: string | null | undefined): string {
  if (!iso) return "Not set";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatRemaining(ms: number): string {
  if (ms <= 0) return "00:00:00";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

function scanLabel(scan: string, quarantined: boolean): string {
  if (quarantined || scan === "INFECTED") return "Quarantined — replace this file";
  if (scan === "CLEAN") return "Scan clean";
  if (scan === "PENDING") return "Scan pending";
  return scan;
}

const LOCKED_STATES = new Set(["ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"]);

function submissionUploadsLocked(submission: SubmissionOut | null): boolean {
  if (!submission) return false;
  if (submission.uploadLocked) return true;
  return LOCKED_STATES.has((submission.state || "").toUpperCase());
}

function canResubmitBeforeDeadline(submission: SubmissionOut | null): boolean {
  if (!submission || !submissionUploadsLocked(submission)) return false;
  const now = Date.now();
  if (submission.timedExpiresAt) {
    const timed = new Date(submission.timedExpiresAt).getTime();
    if (!Number.isNaN(timed) && timed <= now) return false;
  }
  if (!submission.deadlineAt) return false;
  const deadline = new Date(submission.deadlineAt).getTime();
  if (Number.isNaN(deadline)) return false;
  return deadline > now;
}

export default function CompetitorSubmitPage() {
  const params = useParams<{ competitionId: string; stageId: string }>();
  const competitionId = params.competitionId;
  const stageId = params.stageId;

  const [submission, setSubmission] = useState<SubmissionOut | null>(null);
  const [exercise, setExercise] = useState<ExerciseOut | null>(null);
  const [stageMeta, setStageMeta] = useState<MyStageOut | null>(null);
  const [windowBlocked, setWindowBlocked] = useState(false);
  const [finaliseOut, setFinaliseOut] = useState<FinaliseOut | null>(null);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [deliverableCode, setDeliverableCode] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [opening, setOpening] = useState(true);
  const [packPending, setPackPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [remainingMs, setRemainingMs] = useState<number | null>(null);
  const expireCalled = useRef(false);

  const locked = submissionUploadsLocked(submission);
  const resubmitAllowed = canResubmitBeforeDeadline(submission);

  const applyError = useCallback((err: unknown, fallback: string) => {
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
      setFieldErrors({});
    }
  }, []);

  const mergeUpload = useCallback(
    (code: string, filename: string, out: ArtefactUploadOut, progress?: { received: number; total: number }) => {
      setUploads((prev) => {
        const next = prev.filter((u) => u.deliverableCode !== code);
        next.push({
          deliverableCode: code,
          filename,
          artefactId: out.artefactId,
          scan: out.scan,
          quarantined: out.quarantined,
          complete: out.complete,
          progress,
        });
        return next;
      });
    },
    [],
  );

  const runExpire = useCallback(async (submissionId: string) => {
    if (expireCalled.current) return;
    expireCalled.current = true;
    setPending(true);
    setError(null);
    try {
      const out = await expireSubmissionTimer(submissionId);
      setFinaliseOut(out);
      setSubmission((prev) =>
        prev
          ? {
              ...prev,
              state: out.state,
              uploadLocked: true,
              late: out.late,
              hash: out.hash ?? prev.hash,
              receipt: out.receipt ?? prev.receipt,
            }
          : prev,
      );
      setStatusMessage(
        "Timed project ended — submission was captured and further uploads are blocked.",
      );
    } catch (err) {
      expireCalled.current = false;
      applyError(err, "Could not expire submission timer");
    } finally {
      setPending(false);
    }
  }, [applyError]);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      setOpening(true);
      setError(null);
      setFieldErrors({});
      setWindowBlocked(false);
      setStageMeta(null);
      try {
        const pathway = await getMyStages(competitionId).catch(() => null);
        const meta =
          pathway?.stages.find((s) => s.stageId === stageId) ?? null;
        if (cancelled) return;
        if (meta) setStageMeta(meta);

        if (meta?.windowStatus === "upcoming" && !meta.submission.state) {
          setWindowBlocked(true);
          setStatusMessage(
            meta.opensAt
              ? `This exercise becomes available on ${formatDeadline(meta.opensAt)}. Come back then to view the brief and submit.`
              : "This exercise is not available yet. Check back when the stage opens.",
          );
          return;
        }

        const [out, ex] = await Promise.all([
          openSubmission(competitionId, stageId),
          getExercise(competitionId, stageId).catch((err) => {
            if (
              err instanceof ApiError &&
              (err.status === 404 ||
                err.code === "EXERCISE_NOT_FOUND" ||
                err.code === "EXERCISE_NOT_PUBLISHED" ||
                err.code === "WINDOW_CLOSED")
            ) {
              return null;
            }
            throw err;
          }),
        ]);
        if (cancelled) return;
        setSubmission(out);
        setExercise(ex);
        const codes = (ex?.deliverables ?? [])
          .map((d) => d.code?.trim())
          .filter(Boolean);
        if (codes.length > 0) {
          setDeliverableCode((prev) =>
            prev && codes.includes(prev) ? prev : codes[0]!,
          );
        }
        setStatusMessage(
          out.state === "OPEN"
            ? "Submission open — upload required deliverables, then finalise."
            : `Submission state: ${out.state}`,
        );
        if (
          out.timedExpiresAt &&
          new Date(out.timedExpiresAt).getTime() <= Date.now() &&
          !out.uploadLocked &&
          out.state === "OPEN"
        ) {
          await runExpire(out.submissionId);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === "WINDOW_CLOSED") {
          setWindowBlocked(true);
          const pathway = await getMyStages(competitionId).catch(() => null);
          const meta =
            pathway?.stages.find((s) => s.stageId === stageId) ?? null;
          if (meta) setStageMeta(meta);
          setStatusMessage(
            meta?.opensAt
              ? `This exercise becomes available on ${formatDeadline(meta.opensAt)}. Come back then to submit.`
              : "This exercise is not available yet. Check back when the stage opens.",
          );
          setError(null);
          return;
        }
        applyError(err, "Could not open submission");
      } finally {
        if (!cancelled) setOpening(false);
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [competitionId, stageId, applyError, runExpire]);

  useEffect(() => {
    const expiresAt = submission?.timedExpiresAt;
    if (!expiresAt || locked) {
      const clearId = window.setTimeout(() => setRemainingMs(null), 0);
      return () => window.clearTimeout(clearId);
    }
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      const ms = new Date(expiresAt).getTime() - Date.now();
      setRemainingMs(ms);
      if (ms <= 0 && submission?.submissionId) {
        void runExpire(submission.submissionId);
      }
    };
    const immediate = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(immediate);
      window.clearInterval(id);
    };
  }, [submission?.timedExpiresAt, submission?.submissionId, locked, runExpire]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!submission || locked || !file) return;
    const code = deliverableCode.trim();
    if (!code) {
      setFieldErrors({ deliverableCode: "Deliverable code is required" });
      return;
    }
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      let out: ArtefactUploadOut;
      if (file.size >= SUBMISSION_RESUMABLE_THRESHOLD_BYTES) {
        out = await uploadArtefactResumable(submission.submissionId, {
          deliverableCode: code,
          file,
          onProgress: (received, total) => {
            mergeUpload(
              code,
              file.name,
              {
                artefactId: "",
                scan: "PENDING",
                complete: false,
                quarantined: false,
                receivedBytes: received,
              },
              { received, total },
            );
          },
        });
      } else {
        out = await uploadArtefact(submission.submissionId, {
          deliverableCode: code,
          filename: file.name,
          contentType: file.type || null,
          data: file,
        });
      }
      mergeUpload(code, file.name, out, {
        received: out.receivedBytes ?? file.size,
        total: file.size,
      });
      if (out.quarantined || out.scan === "INFECTED") {
        setStatusMessage(
          `File for “${code}” was quarantined. Replace it with a clean file before finalising.`,
        );
      } else {
        setStatusMessage(`Uploaded “${code}” (${out.scan}).`);
        const remaining = (exercise?.deliverables ?? [])
          .map((d) => d.code?.trim())
          .filter(Boolean)
          .filter((c) => {
            if (c === code) return false;
            const existing = uploads.find((u) => u.deliverableCode === c);
            return !(existing?.complete && !existing.quarantined);
          });
        if (remaining[0]) setDeliverableCode(remaining[0]);
      }
      setFile(null);
      const input = document.getElementById(
        "artefactFile",
      ) as HTMLInputElement | null;
      if (input) input.value = "";
    } catch (err) {
      applyError(err, "Could not upload artefact");
    } finally {
      setPending(false);
    }
  }

  async function onFinalise() {
    if (!submission || locked) return;
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await finaliseSubmission(submission.submissionId);
      setFinaliseOut(out);
      setSubmission((prev) =>
        prev
          ? {
              ...prev,
              state: out.state,
              uploadLocked: true,
              late: out.late,
              hash: out.hash ?? prev.hash,
              receipt: out.receipt ?? prev.receipt,
            }
          : prev,
      );
      setStatusMessage(
        out.late
          ? "Submission accepted and marked LATE per competition policy."
          : "Submission accepted. You can still replace it before the deadline.",
      );
    } catch (err) {
      applyError(err, "Could not finalise submission");
    } finally {
      setPending(false);
    }
  }

  async function onResubmit() {
    if (!submission || !resubmitAllowed) return;
    setPending(true);
    setError(null);
    setFieldErrors({});
    setStatusMessage(null);
    try {
      const out = await reopenSubmission(submission.submissionId);
      setSubmission(out);
      setFinaliseOut(null);
      setStatusMessage(
        "Submission reopened — replace artefacts if needed, then finalise again.",
      );
    } catch (err) {
      applyError(err, "Could not reopen submission");
    } finally {
      setPending(false);
    }
  }

  async function onDownloadPack() {
    setPackPending(true);
    setError(null);
    try {
      const { blob, filename } = await downloadExercisePack(competitionId, stageId);
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      applyError(err, "Could not download challenge pack");
    } finally {
      setPackPending(false);
    }
  }

  const displayState = finaliseOut?.state ?? submission?.state ?? null;
  const displayReceipt =
    finaliseOut?.receipt ?? submission?.receipt ?? null;
  const displayHash = finaliseOut?.hash ?? submission?.hash ?? null;
  const configIncomplete = error?.code === "CONFIG_INCOMPLETE";
  const packAvailable = Boolean(exercise?.packFileName);
  const requiredDeliverables = exercise?.deliverables ?? [];
  const selectedDeliverable =
    requiredDeliverables.find((d) => d.code === deliverableCode) ?? null;
  const acceptTypes =
    selectedDeliverable?.allowedTypes &&
    selectedDeliverable.allowedTypes.length > 0
      ? selectedDeliverable.allowedTypes.join(",")
      : undefined;

  function deliverableStatus(code: string): UploadRecord | undefined {
    return uploads.find((u) => u.deliverableCode === code);
  }

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title={exercise?.title ?? "Stage submission"}
        description={
          exercise?.brief
            ? exercise.brief
            : "Upload required deliverables, watch scan and deadline status, then finalise."
        }
      />

      <p className="text-sm text-muted-foreground">
        <Link
          href={`/competitor/competitions/${competitionId}`}
          className="underline-offset-2 hover:underline"
        >
          ← Back to stages
        </Link>
      </p>

      {statusMessage ? (
        <Alert data-testid="submission-status-message">
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert error={error} />

      {windowBlocked ? (
        <Card data-testid="submission-window-blocked">
          <CardHeader>
            <CardTitle className="text-lg">Not available yet</CardTitle>
            <CardDescription>
              The exercise window has not opened for competitors.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="grid gap-2 sm:grid-cols-2">
              <div>
                <dt className="font-medium text-foreground">Available from</dt>
                <dd>{formatDeadline(stageMeta?.opensAt)}</dd>
              </div>
              <div>
                <dt className="font-medium text-foreground">
                  Submission deadline
                </dt>
                <dd>{formatDeadline(stageMeta?.closesAt)}</dd>
              </div>
            </dl>
            <Button variant="outline" className="min-h-11" asChild>
              <Link href={`/competitor/competitions/${competitionId}`}>
                Back to stages
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!windowBlocked && packAvailable ? (
        <Card data-testid="challenge-pack-card">
          <CardHeader>
            <CardTitle className="text-lg">Challenge pack</CardTitle>
            <CardDescription>
              Download the official brief pack for this stage before uploading
              your deliverables.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              className="min-h-11"
              disabled={packPending}
              onClick={() => void onDownloadPack()}
              data-testid="download-challenge-pack"
            >
              {packPending ? "Downloading…" : "Download challenge pack"}
            </Button>
            {exercise?.packFileName ? (
              <p className="mt-2 text-xs text-muted-foreground">
                {exercise.packFileName}
                {exercise.packScanStatus
                  ? ` · scan ${exercise.packScanStatus}`
                  : ""}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {opening ? (
        <p className="text-sm text-muted-foreground" data-testid="submission-opening">
          Opening submission…
        </p>
      ) : null}

      {submission ? (
        <Card data-testid="submission-panel">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
              Submission
              {displayState ? (
                <span data-testid="submission-state">
                  <StatusBadge status={displayState} />
                </span>
              ) : null}
              {(finaliseOut?.late || submission.late) && (
                <StatusBadge status="late" label="Late" />
              )}
            </CardTitle>
            <CardDescription>
              ID{" "}
              <span className="font-mono text-xs" data-testid="submission-id">
                {submission.submissionId}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Submission deadline</dt>
                <dd data-testid="submission-deadline">
                  {formatDeadline(submission.deadlineAt)}
                </dd>
              </div>
              {submission.timedExpiresAt ? (
                <div>
                  <dt className="text-muted-foreground">Timed project ends</dt>
                  <dd>
                    <span data-testid="submission-timed-expires">
                      {formatDeadline(submission.timedExpiresAt)}
                    </span>
                    {remainingMs !== null && !locked ? (
                      <p
                        className="mt-1 font-mono text-base tabular-nums"
                        data-testid="submission-timer"
                        aria-live="polite"
                      >
                        Remaining {formatRemaining(remainingMs)}
                      </p>
                    ) : null}
                  </dd>
                </div>
              ) : null}
            </dl>

            {locked ? (
              <Alert data-testid="submission-locked">
                <AlertTitle>
                  {resubmitAllowed ? "Submission locked" : "Uploads locked"}
                </AlertTitle>
                <AlertDescription className="space-y-3">
                  <p>
                    {resubmitAllowed
                      ? "Your submission is recorded. You can reopen it to replace files until the deadline."
                      : "This submission no longer accepts new artefacts."}
                  </p>
                  {resubmitAllowed ? (
                    <Button
                      type="button"
                      className="min-h-11"
                      disabled={pending}
                      onClick={() => void onResubmit()}
                      data-testid="submission-resubmit"
                    >
                      {pending ? "Reopening…" : "Replace / resubmit"}
                    </Button>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}

            {displayReceipt ? (
              <Alert data-testid="submission-receipt">
                <AlertTitle>Receipt</AlertTitle>
                <AlertDescription>
                  <p className="font-mono break-all" data-testid="submission-receipt-value">
                    {displayReceipt}
                  </p>
                  {displayHash ? (
                    <p className="mt-2 text-xs break-all" data-testid="submission-hash">
                      Hash: {displayHash}
                    </p>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {submission && !locked ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Upload artefact</CardTitle>
            <CardDescription>
              Choose a required deliverable from this exercise, then attach the
              matching file. Large files upload in resumable chunks.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {requiredDeliverables.length > 0 ? (
              <ul
                className="space-y-2 rounded-lg border border-border/70 bg-muted/20 px-3 py-3 text-sm"
                data-testid="submission-deliverable-checklist"
              >
                {requiredDeliverables.map((item) => {
                  const status = deliverableStatus(item.code);
                  const done =
                    Boolean(status?.complete) && !status?.quarantined;
                  const bad = Boolean(status?.quarantined);
                  return (
                    <li
                      key={item.code}
                      className="flex flex-wrap items-center justify-between gap-2"
                    >
                      <span>
                        <span className="font-medium">
                          {item.label?.trim() || item.code}
                        </span>
                        {item.label?.trim() && item.label.trim() !== item.code ? (
                          <span className="ml-2 font-mono text-xs text-muted-foreground">
                            {item.code}
                          </span>
                        ) : null}
                        {item.required !== false ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            Required
                          </span>
                        ) : null}
                      </span>
                      <span
                        className={
                          done
                            ? "text-emerald-700"
                            : bad
                              ? "text-destructive"
                              : "text-muted-foreground"
                        }
                      >
                        {done
                          ? "Uploaded"
                          : bad
                            ? "Replace file"
                            : "Not uploaded"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : null}

            <form
              onSubmit={onUpload}
              className="space-y-4"
              noValidate
              data-testid="submission-upload-form"
            >
              <div className="space-y-2">
                <Label htmlFor="deliverableCode">Deliverable</Label>
                {requiredDeliverables.length > 0 ? (
                  <select
                    id="deliverableCode"
                    className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                    value={deliverableCode}
                    onChange={(e) => setDeliverableCode(e.target.value)}
                    required
                    disabled={pending || configIncomplete}
                    data-testid="submission-deliverable-code"
                    aria-invalid={Boolean(fieldErrors.deliverableCode)}
                    aria-describedby={
                      fieldErrors.deliverableCode
                        ? "deliverableCode-error"
                        : undefined
                    }
                  >
                    {requiredDeliverables.map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.label?.trim()
                          ? `${item.label.trim()} (${item.code})`
                          : item.code}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    id="deliverableCode"
                    className="min-h-11"
                    value={deliverableCode}
                    onChange={(e) => setDeliverableCode(e.target.value)}
                    required
                    autoComplete="off"
                    disabled={pending || configIncomplete}
                    data-testid="submission-deliverable-code"
                    aria-invalid={Boolean(fieldErrors.deliverableCode)}
                    aria-describedby={
                      fieldErrors.deliverableCode
                        ? "deliverableCode-error"
                        : undefined
                    }
                    placeholder="Deliverable code"
                  />
                )}
                <FieldMessage
                  id="deliverableCode-error"
                  message={fieldErrors.deliverableCode}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="artefactFile">File</Label>
                <Input
                  id="artefactFile"
                  type="file"
                  className="min-h-11"
                  accept={acceptTypes}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  required
                  disabled={pending || configIncomplete || !deliverableCode}
                  data-testid="submission-file"
                  aria-describedby="artefactFile-hint"
                />
                <p id="artefactFile-hint" className="text-xs text-muted-foreground">
                  {selectedDeliverable?.allowedTypes?.length
                    ? `Allowed types: ${selectedDeliverable.allowedTypes.join(", ")}`
                    : "Allowed types and size limits are enforced by the server for each deliverable."}
                  {selectedDeliverable?.maxSizeBytes
                    ? ` · Max ${(selectedDeliverable.maxSizeBytes / (1024 * 1024)).toFixed(1)} MB`
                    : ""}
                </p>
                <FieldMessage
                  id="filename-error"
                  message={
                    fieldErrors.filename ||
                    fieldErrors.size ||
                    fieldErrors[deliverableCode.trim()]
                  }
                />
              </div>
              <Button
                type="submit"
                className="min-h-11 w-full"
                disabled={pending || !file || !deliverableCode || configIncomplete}
                data-testid="submission-upload"
              >
                {pending ? "Uploading…" : "Upload"}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {uploads.length > 0 ? (
        <Card data-testid="submission-uploads">
          <CardHeader>
            <CardTitle className="text-lg">Uploaded artefacts</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {uploads.map((u) => (
                <li
                  key={`${u.deliverableCode}-${u.artefactId || u.filename}`}
                  className="rounded-md border border-border p-3 text-sm"
                  data-testid="submission-upload-item"
                  data-deliverable={u.deliverableCode}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium font-mono">{u.deliverableCode}</span>
                    <StatusBadge
                      status={
                        u.quarantined || u.scan === "INFECTED"
                          ? "rejected"
                          : u.scan === "CLEAN"
                            ? "approved"
                            : "pending"
                      }
                      label={u.scan}
                    />
                  </div>
                  <p className="mt-1 text-muted-foreground">{u.filename}</p>
                  <p
                    className="mt-1"
                    data-testid="submission-scan-status"
                  >
                    {scanLabel(u.scan, u.quarantined)}
                  </p>
                  {u.progress && !u.complete ? (
                    <div className="mt-2" data-testid="submission-upload-progress">
                      <div
                        className="h-2 overflow-hidden rounded bg-muted"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={u.progress.total}
                        aria-valuenow={u.progress.received}
                        aria-label={`Upload progress for ${u.deliverableCode}`}
                      >
                        <div
                          className="h-full bg-foreground/80"
                          style={{
                            width: `${Math.min(
                              100,
                              (u.progress.received / u.progress.total) * 100,
                            )}%`,
                          }}
                        />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {u.progress.received} / {u.progress.total} bytes
                      </p>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {submission && !locked ? (
        <Button
          type="button"
          className="min-h-11 w-full"
          disabled={pending || configIncomplete}
          onClick={() => void onFinalise()}
          data-testid="submission-finalise"
        >
          {pending ? "Working…" : "Finalise submission"}
        </Button>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link
          href={`/competitor/competitions/${competitionId}`}
          className="underline underline-offset-2"
          data-testid="submission-back"
        >
          Back to stages
        </Link>
        {" · "}
        <Link href="/competitor" className="underline underline-offset-2">
          Overview
        </Link>
      </p>
    </PageShell>
  );
}
