"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  EyeOffIcon,
  ScaleIcon,
} from "lucide-react";
import {
  ApiError,
  fetchAssessment,
  putScores,
  type AssessmentViewOut,
  type ScorePutOut,
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type MarkDraft = {
  value: string;
  comment: string;
};

function criterionIdOf(c: { criterionId?: string; id?: string }): string {
  return String(c.criterionId ?? c.id ?? "");
}

function criterionMax(c: { max?: number; maxMark?: number }): number | null {
  if (typeof c.max === "number") return c.max;
  if (typeof c.maxMark === "number") return c.maxMark;
  return null;
}

function humanizeCode(code: string): string {
  return code
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function typeLabel(type: string): string {
  const t = type.toUpperCase();
  if (t === "MEASUREMENT") return "Measurement";
  if (t === "JUDGEMENT") return "Judgement";
  return type || "Mark";
}

export default function ExpertScorePage() {
  const params = useParams<{ submissionId: string }>();
  const searchParams = useSearchParams();
  const submissionId = params.submissionId;
  const fromCompetitionId = searchParams.get("from");
  const backHref = fromCompetitionId
    ? `/expert/competitions/${fromCompetitionId}/queue`
    : "/expert";
  const backLabel = fromCompetitionId ? "Back to queue" : "Assessor portal";

  const [view, setView] = useState<AssessmentViewOut | null>(null);
  const [marks, setMarks] = useState<Record<string, MarkDraft>>({});
  const [selectedPenalties, setSelectedPenalties] = useState<string[]>([]);
  const [scoreOut, setScoreOut] = useState<ScorePutOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const out = await fetchAssessment(submissionId);
        if (cancelled) return;
        setView(out);
        const initial: Record<string, MarkDraft> = {};
        for (const c of out.criteria) {
          const id = criterionIdOf(c);
          if (!id) continue;
          const existing = out.myMarks.find((m) => m.criterionId === id);
          initial[id] = {
            value: existing?.value != null ? String(existing.value) : "",
            comment: existing?.comment ?? "",
          };
        }
        setMarks(initial);
        setSelectedPenalties([]);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load assessment",
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
  }, [submissionId]);

  const penaltyOptions = useMemo(() => {
    if (!view) return [];
    return (view.penalties || [])
      .map((p) => ({
        code: String(p.code ?? ""),
        deduction: p.deduction,
      }))
      .filter((p) => p.code);
  }, [view]);

  const criterionRows = useMemo(() => {
    if (!view) return [];
    return view.criteria
      .map((c) => {
        const id = criterionIdOf(c);
        return {
          id,
          name: String(c.name ?? c.label ?? id),
          type: String(c.type ?? "").toUpperCase(),
          max: criterionMax(c),
        };
      })
      .filter((c) => c.id);
  }, [view]);

  const markedCount = useMemo(() => {
    return criterionRows.filter((c) => {
      const v = marks[c.id]?.value?.trim() ?? "";
      return v !== "" && !Number.isNaN(Number(v));
    }).length;
  }, [criterionRows, marks]);

  const allMarked =
    criterionRows.length > 0 && markedCount === criterionRows.length;

  const progressPct =
    criterionRows.length === 0
      ? 0
      : Math.round((markedCount / criterionRows.length) * 100);

  const liveTotal = useMemo(() => {
    if (scoreOut?.total != null) return scoreOut.total;
    let sum = 0;
    let any = false;
    for (const c of criterionRows) {
      const raw = marks[c.id]?.value?.trim() ?? "";
      if (raw === "") continue;
      const n = Number(raw);
      if (Number.isNaN(n)) continue;
      sum += n;
      any = true;
    }
    for (const code of selectedPenalties) {
      const opt = penaltyOptions.find((p) => p.code === code);
      if (opt?.deduction != null) sum -= opt.deduction;
    }
    if (!any && selectedPenalties.length === 0) {
      return view?.total ?? null;
    }
    return sum;
  }, [
    criterionRows,
    marks,
    penaltyOptions,
    scoreOut?.total,
    selectedPenalties,
    view?.total,
  ]);

  async function save(finalize: boolean) {
    if (!view) return;
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      const criterionMarks = view.criteria
        .map((c) => {
          const id = criterionIdOf(c);
          const draft = marks[id];
          if (!draft || draft.value.trim() === "") return null;
          const value = Number(draft.value);
          if (Number.isNaN(value)) return null;
          return {
            criterionId: id,
            type: String(c.type ?? "MEASUREMENT").toUpperCase(),
            value,
            comment: draft.comment.trim() || null,
          };
        })
        .filter(Boolean) as {
        criterionId: string;
        type: string;
        value: number;
        comment: string | null;
      }[];

      const out = await putScores(submissionId, {
        criterionMarks,
        penalties: selectedPenalties.map((code) => ({ code })),
        finalize,
      });
      setScoreOut(out);
      setStatusMessage(
        finalize
          ? `Scores finalised — total ${out.total}.`
          : `Draft saved — total ${out.total}.`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not save scores",
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

  function onSubmitDraft(e: FormEvent) {
    e.preventDefault();
    void save(false);
  }

  const blocked =
    error?.code === "CONFLICT_OF_INTEREST" || error?.code === "NOT_ASSIGNED";

  return (
    <PageShell width="wide" className="space-y-6 pb-28 lg:pb-8">
      <PageHeader
        title={view?.anonCode ? `Score ${view.anonCode}` : "Score submission"}
        description="Enter marks against the exercise rubric. Competitor identity stays hidden when blind mode is on."
        backHref={backHref}
        backLabel={backLabel}
        actions={
          view ? (
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={view.state} />
              {view.blindMode ? (
                <Badge variant="secondary" className="gap-1">
                  <EyeOffIcon className="size-3.5" aria-hidden />
                  Blind mode
                </Badge>
              ) : null}
            </div>
          ) : null
        }
      />

      {statusMessage ? (
        <Alert
          className="rounded-2xl border-border/70"
          data-testid="assessment-status-message"
        >
          <CheckCircle2Icon className="size-4" />
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert error={error} />

      {loading ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-4">
            <Skeleton className="h-28 w-full rounded-2xl" />
            <Skeleton className="h-48 w-full rounded-2xl" />
            <Skeleton className="h-48 w-full rounded-2xl" />
          </div>
          <Skeleton className="hidden h-64 rounded-2xl lg:block" />
        </div>
      ) : null}

      {view && blocked ? (
        <Card className="rounded-3xl border-border/70 shadow-sm">
          <CardContent className="flex flex-col items-start gap-3 py-10 sm:items-center sm:text-center">
            <AlertCircleIcon className="size-10 text-muted-foreground/70" />
            <div className="space-y-1">
              <p className="text-base font-semibold">Scoring unavailable</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {error?.code === "CONFLICT_OF_INTEREST"
                  ? "A conflict of interest blocks you from scoring this submission."
                  : "You are not assigned to score this submission."}
              </p>
            </div>
            <Button asChild variant="outline" className="min-h-11 rounded-2xl">
              <Link href="/expert">Back to portal</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {view && !blocked ? (
        <form
          onSubmit={onSubmitDraft}
          className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
          noValidate
        >
          <div className="space-y-6">
            <Card
              className="rounded-3xl border-border/70 shadow-sm"
              data-testid="assessment-panel"
            >
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">
                  <span data-testid="assessment-anon-code">{view.anonCode}</span>
                </CardTitle>
                <CardDescription>
                  {view.blindMode
                    ? "Anonymised submission — score only against the code and rubric."
                    : "Competitor identity is visible for this assessment."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {view.blindMode ? (
                  <Alert
                    className="rounded-2xl"
                    data-testid="assessment-blind"
                  >
                    <EyeOffIcon className="size-4" />
                    <AlertTitle>Blind assessment</AlertTitle>
                    <AlertDescription>
                      Name, photo, and institution are hidden for this
                      submission.
                    </AlertDescription>
                  </Alert>
                ) : (
                  <dl
                    className="grid gap-3 rounded-2xl bg-muted/50 p-4 text-sm sm:grid-cols-2"
                    data-testid="assessment-identity"
                  >
                    <div>
                      <dt className="text-muted-foreground">Name</dt>
                      <dd className="font-medium">
                        {[view.givenNames, view.familyName]
                          .filter(Boolean)
                          .join(" ") || "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Institution</dt>
                      <dd className="font-medium">
                        {view.institutionId ?? "—"}
                      </dd>
                    </div>
                  </dl>
                )}

                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-muted-foreground">
                      Progress · {markedCount} of {criterionRows.length} marked
                    </span>
                    <span className="font-medium tabular-nums">
                      {progressPct}%
                    </span>
                  </div>
                  <Progress value={progressPct} className="h-2" />
                </div>
              </CardContent>
            </Card>

            <section className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">
                  Criteria
                </h2>
                <p className="text-sm text-muted-foreground">
                  Marks must stay within each maximum. Finalise only when every
                  criterion is marked.
                </p>
              </div>

              <ul className="space-y-4">
                {criterionRows.map((c, index) => {
                  const draft = marks[c.id] ?? { value: "", comment: "" };
                  const filled =
                    draft.value.trim() !== "" &&
                    !Number.isNaN(Number(draft.value));
                  const overMax =
                    filled &&
                    c.max != null &&
                    Number(draft.value) > c.max;
                  return (
                    <li key={c.id}>
                      <Card
                        className={cn(
                          "rounded-3xl border-border/70 shadow-sm transition-colors",
                          filled && !overMax && "ring-1 ring-brand-green/25",
                          overMax && "ring-1 ring-destructive/30",
                        )}
                        data-testid="assessment-criterion"
                        data-criterion={c.id}
                      >
                        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0 pb-3">
                          <div className="min-w-0 space-y-1.5">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                Criterion {index + 1}
                              </span>
                              <Badge variant="outline">
                                {typeLabel(c.type)}
                              </Badge>
                              {c.max != null ? (
                                <Badge variant="secondary">
                                  Max {c.max}
                                </Badge>
                              ) : null}
                            </div>
                            <CardTitle className="text-base font-semibold leading-snug">
                              {c.name}
                            </CardTitle>
                          </div>
                          {filled && !overMax ? (
                            <CheckCircle2Icon
                              className="size-5 shrink-0 text-brand-green"
                              aria-label="Marked"
                            />
                          ) : null}
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div className="space-y-2">
                            <Label htmlFor={`mark-${c.id}`}>Mark</Label>
                            <Input
                              id={`mark-${c.id}`}
                              type="number"
                              inputMode="numeric"
                              className="min-h-12 max-w-48 rounded-2xl text-lg font-semibold tabular-nums"
                              value={draft.value}
                              onChange={(e) =>
                                setMarks((prev) => ({
                                  ...prev,
                                  [c.id]: {
                                    ...draft,
                                    value: e.target.value,
                                  },
                                }))
                              }
                              min={0}
                              max={c.max ?? undefined}
                              disabled={pending}
                              data-testid="assessment-mark"
                              aria-invalid={Boolean(
                                fieldErrors[c.id] || overMax,
                              )}
                              aria-describedby={
                                fieldErrors[c.id] || overMax
                                  ? `${c.id}-error`
                                  : undefined
                              }
                            />
                            {overMax ? (
                              <p
                                id={`${c.id}-error`}
                                className="text-sm text-destructive"
                              >
                                Mark cannot exceed {c.max}.
                              </p>
                            ) : (
                              <FieldMessage
                                id={`${c.id}-error`}
                                message={fieldErrors[c.id]}
                              />
                            )}
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor={`comment-${c.id}`}>
                              Comment{" "}
                              <span className="font-normal text-muted-foreground">
                                (optional)
                              </span>
                            </Label>
                            <Textarea
                              id={`comment-${c.id}`}
                              value={draft.comment}
                              onChange={(e) =>
                                setMarks((prev) => ({
                                  ...prev,
                                  [c.id]: {
                                    ...draft,
                                    comment: e.target.value,
                                  },
                                }))
                              }
                              disabled={pending}
                              rows={2}
                              className="rounded-2xl"
                              placeholder="Brief justification…"
                              data-testid="assessment-comment"
                            />
                          </div>
                        </CardContent>
                      </Card>
                    </li>
                  );
                })}
              </ul>
            </section>

            {penaltyOptions.length > 0 ? (
              <Card className="rounded-3xl border-border/70 shadow-sm">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <ScaleIcon className="size-5 text-muted-foreground" />
                    Penalties
                  </CardTitle>
                  <CardDescription>
                    Apply configured deductions. Caps are enforced when you
                    save.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {penaltyOptions.map((p) => {
                    const checked = selectedPenalties.includes(p.code);
                    return (
                      <label
                        key={p.code}
                        className={cn(
                          "flex min-h-12 cursor-pointer items-center gap-3 rounded-2xl border border-border/70 px-4 text-sm transition-colors",
                          checked
                            ? "bg-muted/80 ring-1 ring-foreground/10"
                            : "hover:bg-muted/40",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            setSelectedPenalties((prev) =>
                              v
                                ? [...prev, p.code]
                                : prev.filter((code) => code !== p.code),
                            );
                          }}
                          disabled={pending}
                          data-testid="assessment-penalty"
                        />
                        <span className="flex-1 font-medium">
                          {humanizeCode(p.code)}
                        </span>
                        {p.deduction != null ? (
                          <span className="tabular-nums text-muted-foreground">
                            −{p.deduction}
                          </span>
                        ) : null}
                      </label>
                    );
                  })}
                </CardContent>
              </Card>
            ) : null}

            {scoreOut?.breakdown ? (
              <Card
                className="rounded-3xl border-border/70 shadow-sm"
                data-testid="assessment-breakdown"
              >
                <CardHeader>
                  <CardTitle className="text-lg">Last saved breakdown</CardTitle>
                  <CardDescription>
                    From the server after your most recent save.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <ul className="divide-y divide-border/70 rounded-2xl border border-border/70">
                    {scoreOut.breakdown.marks.map((m) => {
                      const name =
                        criterionRows.find((c) => c.id === m.criterionId)
                          ?.name ?? m.criterionId;
                      return (
                        <li
                          key={`${m.criterionId}-${m.assessorId}`}
                          className="flex items-center justify-between gap-3 px-4 py-3"
                        >
                          <span className="min-w-0 truncate">{name}</span>
                          <span className="shrink-0 tabular-nums text-muted-foreground">
                            {m.value ?? "—"} · {m.status}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  {scoreOut.breakdown.penalties.length > 0 ? (
                    <ul
                      className="space-y-1 text-muted-foreground"
                      data-testid="assessment-penalty-list"
                    >
                      {scoreOut.breakdown.penalties.map((p) => (
                        <li key={p.code}>
                          {humanizeCode(p.code)}: −{p.deduction}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="text-base">
                    Breakdown total:{" "}
                    <strong
                      className="tabular-nums"
                      data-testid="assessment-breakdown-total"
                    >
                      {scoreOut.breakdown.total}
                    </strong>
                  </p>
                </CardContent>
              </Card>
            ) : null}

            <p className="text-sm text-muted-foreground lg:hidden">
              <Link
                href={`/expert/submissions/${submissionId}/moderation`}
                className="underline underline-offset-2"
              >
                Open moderation
              </Link>
            </p>
          </div>

          <aside className="lg:sticky lg:top-20 lg:self-start">
            <Card className="rounded-3xl border-border/70 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Scoring summary</CardTitle>
                <CardDescription>
                  {allMarked
                    ? "All criteria marked — ready to finalise."
                    : `${criterionRows.length - markedCount} of ${criterionRows.length} still unmarked.`}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-2xl bg-muted/60 px-4 py-5 text-center">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    {scoreOut ? "Saved total" : "Running total"}
                  </p>
                  <p
                    className="mt-1 text-4xl font-bold tracking-tight tabular-nums"
                    data-testid="assessment-total"
                  >
                    {liveTotal != null ? liveTotal : "—"}
                  </p>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Marked</span>
                    <span className="font-medium tabular-nums">
                      {markedCount}/{criterionRows.length}
                    </span>
                  </div>
                  <Progress value={progressPct} className="h-2" />
                </div>

                <div className="flex flex-col gap-2">
                  <Button
                    type="submit"
                    variant="outline"
                    className="min-h-11 rounded-2xl"
                    disabled={pending}
                    data-testid="assessment-save-draft"
                  >
                    {pending ? "Saving…" : "Save draft"}
                  </Button>
                  <Button
                    type="button"
                    className="min-h-11 rounded-2xl"
                    disabled={pending || !allMarked}
                    onClick={() => void save(true)}
                    data-testid="assessment-finalise"
                  >
                    {pending ? "Working…" : "Finalise scores"}
                  </Button>
                  {!allMarked ? (
                    <p className="text-xs text-muted-foreground">
                      Finalise unlocks when every criterion has a mark.
                    </p>
                  ) : null}
                </div>

                <Button
                  asChild
                  variant="ghost"
                  className="hidden min-h-10 w-full rounded-2xl lg:inline-flex"
                >
                  <Link
                    href={`/expert/submissions/${submissionId}/moderation`}
                  >
                    Open moderation
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </aside>

          {/* Mobile sticky actions */}
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border/70 bg-card/95 p-3 backdrop-blur lg:hidden">
            <div className="mx-auto flex max-w-lg items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-[0.7rem] uppercase tracking-wider text-muted-foreground">
                  Total
                </p>
                <p className="truncate text-lg font-bold tabular-nums">
                  {liveTotal != null ? liveTotal : "—"}
                </p>
              </div>
              <Button
                type="submit"
                variant="outline"
                className="min-h-11 rounded-2xl"
                disabled={pending}
              >
                Draft
              </Button>
              <Button
                type="button"
                className="min-h-11 rounded-2xl"
                disabled={pending || !allMarked}
                onClick={() => void save(true)}
              >
                Finalise
              </Button>
            </div>
          </div>
        </form>
      ) : null}

      {!loading && !view && !blocked ? (
        <p className="text-sm text-muted-foreground">
          <Link
            href="/expert"
            className="underline underline-offset-2"
            data-testid="assessment-back"
          >
            Back to assessor portal
          </Link>
        </p>
      ) : null}
    </PageShell>
  );
}
