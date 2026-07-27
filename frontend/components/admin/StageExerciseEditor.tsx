"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  DeliverableItem,
  ExerciseOut,
  deleteExercisePack,
  downloadExercisePack,
  getExercise,
  publishExercise,
  putExercise,
  triggerBrowserDownload,
  unpublishExercise,
  uploadExercisePack,
} from "@/lib/api";
import { ExerciseRubricEditor } from "@/components/admin/ExerciseRubricEditor";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const NONE_VALUE = "__none__";

type DeliverableDraft = {
  code: string;
  label: string;
  required: boolean;
  allowedTypes: string;
  maxSizeBytes: string;
};

function emptyDeliverable(): DeliverableDraft {
  return {
    code: "",
    label: "",
    required: true,
    allowedTypes: "pdf,zip",
    maxSizeBytes: "",
  };
}

function draftFromExercise(d: DeliverableItem): DeliverableDraft {
  return {
    code: d.code,
    label: d.label ?? "",
    required: d.required !== false,
    allowedTypes: (d.allowedTypes ?? []).join(","),
    maxSizeBytes: d.maxSizeBytes != null ? String(d.maxSizeBytes) : "",
  };
}

function draftsToPayload(rows: DeliverableDraft[]): DeliverableItem[] {
  return rows
    .filter((r) => r.code.trim())
    .map((r) => {
      const types = r.allowedTypes
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const maxRaw = r.maxSizeBytes.trim();
      return {
        code: r.code.trim(),
        label: r.label.trim() || null,
        required: r.required,
        allowedTypes: types,
        maxSizeBytes: maxRaw === "" ? null : Number(maxRaw),
      };
    });
}

export type StageExerciseEditorProps = {
  competitionId: string;
  stageId: string;
  onStatusChange?: (status: string | null) => void;
};

export function StageExerciseEditor({
  competitionId,
  stageId,
  onStatusChange,
}: StageExerciseEditorProps) {
  const [exercise, setExercise] = useState<ExerciseOut | null>(null);
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [schemeId, setSchemeId] = useState<string | null>(null);
  const [latePolicy, setLatePolicy] = useState("");
  const [deliverables, setDeliverables] = useState<DeliverableDraft[]>([
    emptyDeliverable(),
  ]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [packPending, setPackPending] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const packInputRef = useRef<HTMLInputElement>(null);

  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  function applyExercise(ex: ExerciseOut) {
    setExercise(ex);
    setTitle(ex.title);
    setBrief(ex.brief ?? "");
    setSchemeId(ex.schemeId ?? null);
    setLatePolicy(ex.latePolicy ?? "");
    setDeliverables(
      ex.deliverables.length > 0
        ? ex.deliverables.map(draftFromExercise)
        : [emptyDeliverable()],
    );
    onStatusChangeRef.current?.(ex.status ?? null);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const ex = await getExercise(competitionId, stageId);
        if (!cancelled) applyExercise(ex);
      } catch (err) {
        if (
          err instanceof ApiError &&
          (err.status === 404 || err.code === "EXERCISE_NOT_FOUND")
        ) {
          setTitle("");
          setBrief("");
          setSchemeId(null);
          setLatePolicy("");
          setDeliverables([emptyDeliverable()]);
          setExercise(null);
          onStatusChangeRef.current?.(null);
        } else if (!cancelled && err instanceof ApiError) {
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, stageId]);

  function updateDeliverable(index: number, patch: Partial<DeliverableDraft>) {
    setDeliverables((prev) =>
      prev.map((d, i) => (i === index ? { ...d, ...patch } : d)),
    );
  }

  function addDeliverable() {
    setDeliverables((prev) => [...prev, emptyDeliverable()]);
  }

  function removeDeliverable(index: number) {
    setDeliverables((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== index);
    });
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    setPending(true);
    try {
      const out = await putExercise(competitionId, stageId, {
        title: title.trim(),
        brief: brief.trim() || null,
        deliverables: draftsToPayload(deliverables),
        schemeId,
        latePolicy: latePolicy.trim() || null,
      });
      applyExercise(out);
      setSavedMessage("Exercise saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  async function onPublish() {
    setActionPending(true);
    setError(null);
    try {
      const out = await publishExercise(competitionId, stageId);
      applyExercise(out);
      setSavedMessage("Exercise published.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setActionPending(false);
    }
  }

  async function onUnpublish() {
    setActionPending(true);
    setError(null);
    try {
      const out = await unpublishExercise(competitionId, stageId);
      applyExercise(out);
      setSavedMessage("Exercise unpublished (draft).");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setActionPending(false);
    }
  }

  async function onPackUpload(file: File | null) {
    if (!file) return;
    setPackPending(true);
    setError(null);
    setSavedMessage(null);
    try {
      const out = await uploadExercisePack(competitionId, stageId, file);
      applyExercise(out);
      setSavedMessage("Challenge pack uploaded.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPackPending(false);
      if (packInputRef.current) packInputRef.current.value = "";
    }
  }

  async function onPackRemove() {
    setPackPending(true);
    setError(null);
    setSavedMessage(null);
    try {
      const out = await deleteExercisePack(competitionId, stageId);
      applyExercise(out);
      setSavedMessage("Challenge pack removed.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPackPending(false);
    }
  }

  async function onPackDownload() {
    setPackPending(true);
    setError(null);
    try {
      const { blob, filename } = await downloadExercisePack(
        competitionId,
        stageId,
      );
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPackPending(false);
    }
  }

  const status = exercise?.status ?? "—";
  const isPublished = status === "PUBLISHED";
  const hasPack = Boolean(exercise?.packFileName);

  if (loading) {
    return <Skeleton className="h-48 w-full" />;
  }

  return (
    <div className="space-y-8">
      <ApiErrorAlert error={error} />

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Exercise content
            </h3>
            <p className="text-sm text-muted-foreground">
              Save as draft, then publish when ready for submissions.
            </p>
          </div>
          {exercise ? (
            <Badge variant={isPublished ? "success" : "secondary"}>
              {status}
            </Badge>
          ) : null}
        </div>

        <form onSubmit={onSave} className="space-y-6" noValidate>
          <div className="space-y-2">
            <Label htmlFor="exercise-title">Title</Label>
            <Input
              id="exercise-title"
              className="min-h-11"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
            <FieldMessage message={fieldErrors.title} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="exercise-brief">Brief (optional)</Label>
            <Textarea
              id="exercise-brief"
              rows={4}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Late policy (optional)</Label>
            <Select
              value={latePolicy || NONE_VALUE}
              onValueChange={(v) =>
                setLatePolicy(v === NONE_VALUE ? "" : v)
              }
            >
              <SelectTrigger className="min-h-11 w-full">
                <SelectValue placeholder="Default" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE_VALUE}>Default</SelectItem>
                <SelectItem value="block">Block late</SelectItem>
                <SelectItem value="flag-late">Flag late</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-4 border-t border-border pt-6">
            <ExerciseRubricEditor
              competitionId={competitionId}
              stageId={stageId}
              schemeId={schemeId}
              exerciseTitle={title}
              onSchemeChange={(scheme) => {
                setSchemeId(scheme?.schemeId ?? null);
              }}
            />
            <FieldMessage message={fieldErrors.schemeId} />
          </div>

          <div className="space-y-4 border-t border-border pt-6">
            <div>
              <p className="text-sm font-medium">Deliverables</p>
              <p className="text-sm text-muted-foreground">
                One row per required upload or artifact.
              </p>
            </div>
            {deliverables.map((row, index) => (
              <div
                key={index}
                className="space-y-3 border-t border-border pt-4 first:border-t-0 first:pt-0"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">
                    Deliverable {index + 1}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={deliverables.length <= 1}
                    onClick={() => removeDeliverable(index)}
                  >
                    Remove
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Code</Label>
                    <Input
                      value={row.code}
                      placeholder="main"
                      onChange={(e) =>
                        updateDeliverable(index, { code: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Label (optional)</Label>
                    <Input
                      value={row.label}
                      onChange={(e) =>
                        updateDeliverable(index, { label: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Allowed types (comma-separated)</Label>
                    <Input
                      value={row.allowedTypes}
                      onChange={(e) =>
                        updateDeliverable(index, {
                          allowedTypes: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Max size bytes (optional)</Label>
                    <Input
                      inputMode="numeric"
                      value={row.maxSizeBytes}
                      onChange={(e) =>
                        updateDeliverable(index, {
                          maxSizeBytes: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Required</Label>
                    <Select
                      value={row.required ? "yes" : "no"}
                      onValueChange={(v) =>
                        updateDeliverable(index, { required: v === "yes" })
                      }
                    >
                      <SelectTrigger className="min-h-11 w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="yes">Yes</SelectItem>
                        <SelectItem value="no">No</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" onClick={addDeliverable}>
              Add deliverable
            </Button>
          </div>

          <div className="flex flex-wrap gap-3 border-t border-border pt-6">
            <Button type="submit" className="min-h-11" disabled={pending}>
              {pending ? "Saving…" : "Save exercise"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="min-h-11"
              disabled={actionPending || isPublished}
              onClick={() => void onPublish()}
            >
              Publish
            </Button>
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={actionPending || !isPublished}
              onClick={() => void onUnpublish()}
            >
              Unpublish
            </Button>
          </div>

          {savedMessage ? (
            <Alert>
              <AlertTitle>Updated</AlertTitle>
              <AlertDescription>{savedMessage}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </section>

      <Separator />

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            Challenge pack
          </h3>
          <p className="text-sm text-muted-foreground">
            Upload a PDF or DOCX pack competitors can download for this stage.
          </p>
        </div>
        {hasPack ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">File</dt>
              <dd className="font-medium">{exercise?.packFileName}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Scan status</dt>
              <dd>{exercise?.packScanStatus ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Content type</dt>
              <dd>{exercise?.packContentType ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">
            No challenge pack uploaded yet. Save the exercise first if this
            stage has no exercise record.
          </p>
        )}
        <input
          ref={packInputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          onChange={(e) => {
            void onPackUpload(e.target.files?.[0] ?? null);
          }}
        />
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            className="min-h-11"
            disabled={packPending || !exercise}
            onClick={() => packInputRef.current?.click()}
          >
            {packPending
              ? "Working…"
              : hasPack
                ? "Replace pack"
                : "Upload pack"}
          </Button>
          {hasPack ? (
            <>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11"
                disabled={packPending}
                onClick={() => void onPackDownload()}
              >
                Download
              </Button>
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                disabled={packPending}
                onClick={() => void onPackRemove()}
              >
                Remove
              </Button>
            </>
          ) : null}
        </div>
      </section>

    </div>
  );
}