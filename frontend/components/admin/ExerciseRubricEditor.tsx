"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createMarkingScheme,
  deleteMarkingSchemeDocument,
  downloadMarkingSchemeDocument,
  getExercise,
  getExerciseRubric,
  listMarkingSchemes,
  putExercise,
  putExerciseRubric,
  triggerBrowserDownload,
  uploadMarkingSchemeDocument,
  type MarkingSchemeOut,
  type RubricCriterion,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type CriterionDraft = {
  key: string;
  id: string;
  name: string;
  type: string;
  max: string;
};

function newKey() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function emptyCriterion(): CriterionDraft {
  return { key: newKey(), id: "", name: "", type: "JUDGEMENT", max: "" };
}

function isDefaultOverall(criteria: RubricCriterion[]): boolean {
  if (criteria.length !== 1) return false;
  const c = criteria[0];
  return (
    (c.id === "c_overall" || c.name === "Overall") &&
    String(c.type).toUpperCase() === "JUDGEMENT" &&
    Number(c.max) === 100
  );
}

type ExerciseRubricEditorProps = {
  competitionId: string;
  stageId: string;
  schemeId: string | null;
  exerciseTitle: string;
  onSchemeChange?: (scheme: MarkingSchemeOut | null) => void;
};

/**
 * Optional rubric document + optional scoring criteria.
 * If no custom criteria are saved, experts score a single Overall mark (max 100).
 */
export function ExerciseRubricEditor({
  competitionId,
  stageId,
  schemeId,
  exerciseTitle,
  onSchemeChange,
}: ExerciseRubricEditorProps) {
  const [scheme, setScheme] = useState<MarkingSchemeOut | null>(null);
  const [blindMode, setBlindMode] = useState(true);
  const [criteria, setCriteria] = useState<CriterionDraft[]>([]);
  const [usingDefault, setUsingDefault] = useState(true);
  const [loading, setLoading] = useState(true);
  const [docPending, setDocPending] = useState(false);
  const [criteriaPending, setCriteriaPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        let schemeRow: MarkingSchemeOut | null = null;
        if (schemeId) {
          const schemes = await listMarkingSchemes(competitionId);
          if (cancelled) return;
          schemeRow = schemes.find((s) => s.schemeId === schemeId) ?? null;
        }
        if (!cancelled) setScheme(schemeRow);

        try {
          const rubric = await getExerciseRubric(competitionId, stageId);
          if (cancelled) return;
          setBlindMode(rubric.blindMode);
          if (!rubric.criteria.length || isDefaultOverall(rubric.criteria)) {
            setCriteria([]);
            setUsingDefault(true);
          } else {
            setUsingDefault(false);
            setCriteria(
              rubric.criteria.map((c) => ({
                key: newKey(),
                id: c.id ?? "",
                name: c.name,
                type: c.type || "JUDGEMENT",
                max: String(c.max),
              })),
            );
          }
        } catch (err) {
          if (cancelled) return;
          if (
            err instanceof ApiError &&
            (err.status === 404 || err.code === "NOT_FOUND")
          ) {
            setBlindMode(true);
            setCriteria([]);
            setUsingDefault(true);
          } else if (err instanceof ApiError) {
            setError(err);
          }
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, stageId, schemeId]);

  async function ensureSchemeAttached(): Promise<string> {
    if (schemeId) return schemeId;

    const title = exerciseTitle.trim() || "Exercise";
    const created = await createMarkingScheme(competitionId, {
      name: `Rubric — ${title}`.slice(0, 120),
    });

    try {
      const ex = await getExercise(competitionId, stageId);
      await putExercise(competitionId, stageId, {
        title: ex.title || title,
        brief: ex.brief ?? null,
        deliverables: ex.deliverables ?? [],
        schemeId: created.schemeId,
        latePolicy: ex.latePolicy ?? null,
        timedDurationSeconds: ex.timedDurationSeconds ?? null,
      });
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.status === 404 || err.code === "EXERCISE_NOT_FOUND")
      ) {
        await putExercise(competitionId, stageId, {
          title,
          schemeId: created.schemeId,
          deliverables: [],
        });
      } else {
        throw err;
      }
    }

    setScheme(created);
    onSchemeChange?.(created);
    return created.schemeId;
  }

  async function onUpload(file: File | null) {
    if (!file) return;
    setDocPending(true);
    setError(null);
    setSavedMessage(null);
    try {
      const id = await ensureSchemeAttached();
      const updated = await uploadMarkingSchemeDocument(
        competitionId,
        id,
        file,
      );
      setScheme(updated);
      onSchemeChange?.(updated);
      setSavedMessage("Rubric document uploaded.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setDocPending(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function onRemoveDoc() {
    if (!scheme?.schemeId) return;
    setDocPending(true);
    setError(null);
    setSavedMessage(null);
    try {
      const updated = await deleteMarkingSchemeDocument(
        competitionId,
        scheme.schemeId,
      );
      setScheme(updated);
      onSchemeChange?.(updated);
      setSavedMessage("Rubric document removed.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setDocPending(false);
    }
  }

  async function onDownload() {
    if (!scheme?.schemeId) return;
    setDocPending(true);
    setError(null);
    try {
      const { blob, filename } = await downloadMarkingSchemeDocument(
        competitionId,
        scheme.schemeId,
      );
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setDocPending(false);
    }
  }

  async function onSaveCriteria() {
    setCriteriaPending(true);
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    try {
      await ensureSchemeAttached();
      const named = criteria.filter((c) => c.name.trim());
      const payload: RubricCriterion[] =
        named.length === 0
          ? [{ id: "c_overall", name: "Overall", type: "JUDGEMENT", max: 100 }]
          : named.map((c, idx) => ({
              id: c.id.trim() || `c${idx + 1}`,
              name: c.name.trim(),
              type: c.type,
              max: Number(c.max) || 1,
            }));

      const out = await putExerciseRubric(competitionId, stageId, {
        blindMode,
        criteria: payload,
        penalties: [],
      });
      onSchemeChange?.({
        schemeId: out.schemeId,
        competitionId: out.competitionId,
        name: out.name,
        blindMode: out.blindMode,
        criteria: out.criteria,
        penalties: out.penalties,
        hasRubricCriteria: out.hasRubricCriteria,
        documentFileName: scheme?.documentFileName,
        documentContentType: scheme?.documentContentType,
        documentScanStatus: scheme?.documentScanStatus,
      });
      setUsingDefault(isDefaultOverall(payload));
      if (isDefaultOverall(payload)) {
        setCriteria([]);
        setSavedMessage(
          "Using default single Overall score (max 100) for experts.",
        );
      } else {
        setSavedMessage(`Saved ${payload.length} scoring criteria.`);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setCriteriaPending(false);
    }
  }

  function onResetToDefault() {
    setCriteria([]);
    setUsingDefault(true);
    void (async () => {
      setCriteriaPending(true);
      setError(null);
      setSavedMessage(null);
      try {
        await ensureSchemeAttached();
        const out = await putExerciseRubric(competitionId, stageId, {
          blindMode,
          criteria: [
            { id: "c_overall", name: "Overall", type: "JUDGEMENT", max: 100 },
          ],
          penalties: [],
        });
        onSchemeChange?.({
          schemeId: out.schemeId,
          competitionId: out.competitionId,
          name: out.name,
          blindMode: out.blindMode,
          criteria: out.criteria,
          penalties: out.penalties,
          hasRubricCriteria: out.hasRubricCriteria,
          documentFileName: scheme?.documentFileName,
          documentContentType: scheme?.documentContentType,
          documentScanStatus: scheme?.documentScanStatus,
        });
        setSavedMessage(
          "Reset to default single Overall score (max 100).",
        );
      } catch (err) {
        if (err instanceof ApiError) setError(err);
      } finally {
        setCriteriaPending(false);
      }
    })();
  }

  const hasDoc = Boolean(scheme?.documentFileName);
  const pending = docPending || criteriaPending;

  if (loading) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Loading rubric…
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div>
          <p className="text-sm font-medium">Rubric document</p>
          <p className="text-sm text-muted-foreground">
            Optional PDF or DOCX for this exercise. Skill-area criteria for
            competitors and institutions are uploaded on the skill page.
          </p>
        </div>

        <ApiErrorAlert error={error} />

        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Document</dt>
            <dd className="font-medium">
              {scheme?.documentFileName ?? "None"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Scan status</dt>
            <dd>
              {scheme?.documentScanStatus ? (
                <Badge variant="secondary">{scheme.documentScanStatus}</Badge>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>

        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          onChange={(e) => {
            void onUpload(e.target.files?.[0] ?? null);
          }}
        />

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={pending}
            onClick={() => inputRef.current?.click()}
            data-testid="exercise-rubric-upload"
          >
            {docPending
              ? "Working…"
              : hasDoc
                ? "Replace document"
                : "Upload document"}
          </Button>
          {hasDoc ? (
            <>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11"
                disabled={pending}
                onClick={() => void onDownload()}
              >
                Download
              </Button>
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                disabled={pending}
                onClick={() => void onRemoveDoc()}
              >
                Remove
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <div>
          <p className="text-sm font-medium">Scoring criteria</p>
          <p className="text-sm text-muted-foreground">
            Optional. If you do not add criteria, experts score a single{" "}
            <span className="font-medium text-foreground">
              Overall
            </span>{" "}
            mark (judgement · max 100).
          </p>
        </div>

        {usingDefault && criteria.length === 0 ? (
          <p
            className="rounded-xl bg-muted/50 px-3 py-2 text-sm text-muted-foreground"
            data-testid="exercise-criteria-default-hint"
          >
            Default in use: Overall (JUDGEMENT · max 100). Add criteria below
            only if this exercise needs a breakdown.
          </p>
        ) : null}

        <div className="flex items-center gap-2">
          <Checkbox
            id="blindMode"
            checked={blindMode}
            onCheckedChange={(v) => setBlindMode(v === true)}
          />
          <Label htmlFor="blindMode">
            Blind mode (hide competitor identity while scoring)
          </Label>
        </div>

        <FieldMessage message={fieldErrors.criteria ?? fieldErrors.rubric} />

        {criteria.map((row, index) => (
          <div
            key={row.key}
            className="grid gap-2 rounded-xl border border-border/70 p-3 sm:grid-cols-12"
          >
            <div className="space-y-1 sm:col-span-4">
              <Label>Name</Label>
              <Input
                className="min-h-10"
                value={row.name}
                onChange={(e) => {
                  setUsingDefault(false);
                  setCriteria((prev) =>
                    prev.map((c, i) =>
                      i === index ? { ...c, name: e.target.value } : c,
                    ),
                  );
                }}
                placeholder="Accuracy"
              />
            </div>
            <div className="space-y-1 sm:col-span-3">
              <Label>Type</Label>
              <Select
                value={row.type}
                onValueChange={(value) => {
                  if (!value) return;
                  setUsingDefault(false);
                  setCriteria((prev) =>
                    prev.map((c, i) =>
                      i === index ? { ...c, type: value } : c,
                    ),
                  );
                }}
              >
                <SelectTrigger className="min-h-10 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MEASUREMENT">Measurement</SelectItem>
                  <SelectItem value="JUDGEMENT">Judgement</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label>Max</Label>
              <Input
                type="number"
                min={1}
                className="min-h-10"
                value={row.max}
                onChange={(e) => {
                  setUsingDefault(false);
                  setCriteria((prev) =>
                    prev.map((c, i) =>
                      i === index ? { ...c, max: e.target.value } : c,
                    ),
                  );
                }}
              />
            </div>
            <div className="flex items-end sm:col-span-3">
              <Button
                type="button"
                variant="outline"
                className="min-h-10 w-full"
                onClick={() => {
                  setCriteria((prev) => {
                    const next = prev.filter((_, i) => i !== index);
                    if (next.length === 0) setUsingDefault(true);
                    return next;
                  });
                }}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            className="min-h-10"
            onClick={() => {
              setUsingDefault(false);
              setCriteria((prev) => [...prev, emptyCriterion()]);
            }}
            data-testid="exercise-criteria-add"
          >
            Add criterion
          </Button>
          <Button
            type="button"
            className="min-h-10"
            disabled={pending}
            onClick={() => void onSaveCriteria()}
            data-testid="exercise-criteria-save"
          >
            {criteriaPending ? "Saving…" : "Save criteria"}
          </Button>
          {!usingDefault || criteria.length > 0 ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-10"
              disabled={pending}
              onClick={onResetToDefault}
              data-testid="exercise-criteria-reset-default"
            >
              Use default Overall score
            </Button>
          ) : null}
        </div>
      </div>

      {savedMessage ? (
        <p className="text-sm text-muted-foreground" role="status">
          {savedMessage}
        </p>
      ) : null}
    </div>
  );
}
