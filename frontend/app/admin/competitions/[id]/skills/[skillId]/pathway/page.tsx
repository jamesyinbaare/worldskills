"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import {
  ApiError,
  type StagePathwayItem,
  type ZoneOut,
  getPathway,
  listCycleZones,
  putPathway,
} from "@/lib/api";
import { parseQuotaText } from "@/lib/pathway";
import { StageExerciseDialog } from "@/components/admin/StageExerciseDialog";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
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

type SelectionMode = "PER_ZONE" | "NATIONAL_POOL";

type StageDraft = {
  stageId?: string;
  order: string;
  type: string;
  selectionMode: SelectionMode;
  opensAt: string;
  closesAt: string;
  quotaByZone: string;
  quota: string;
  minScore: string;
  exerciseStatus?: string | null;
};

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInput(local: string): string | null {
  const trimmed = local.trim();
  if (!trimmed) return null;
  const d = new Date(trimmed);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function emptyStage(order: number): StageDraft {
  return {
    order: String(order),
    type: "VIRTUAL",
    selectionMode: "PER_ZONE",
    opensAt: "",
    closesAt: "",
    quotaByZone: "",
    quota: "",
    minScore: "",
    exerciseStatus: null,
  };
}

function formatQuotaByZone(
  map: Record<string, number> | null | undefined,
): string {
  if (!map) return "";
  return Object.entries(map)
    .map(([zone, amount]) => `${zone}:${amount}`)
    .join("\n");
}

function exerciseStatusLabel(status: string | null | undefined): string {
  if (!status) return "No exercise";
  return status;
}

function exerciseBadgeVariant(
  status: string | null | undefined,
): "success" | "secondary" | "outline" {
  if (status === "PUBLISHED") return "success";
  if (status) return "secondary";
  return "outline";
}

export default function PathwayEditorPage() {
  const params = useParams<{ id: string; skillId: string }>();
  const competitionId = params.id;
  const skillId = params.skillId;

  const [stages, setStages] = useState<StageDraft[]>([emptyStage(1)]);
  const [zones, setZones] = useState<ZoneOut[]>([]);
  const [finalists, setFinalists] = useState<number | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [exerciseStageIndex, setExerciseStageIndex] = useState<number | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [pathway, cycleZones] = await Promise.all([
          getPathway(competitionId, skillId),
          listCycleZones(competitionId),
        ]);
        if (cancelled) return;
        setZones(cycleZones.filter((z) => z.active));
        if (pathway.stages.length > 0) {
          setStages(
            pathway.stages.map((s) => ({
              stageId: s.stageId,
              order: String(s.order),
              type: s.type === "PHYSICAL" ? "PHYSICAL" : "VIRTUAL",
              selectionMode:
                s.selectionMode === "NATIONAL_POOL"
                  ? "NATIONAL_POOL"
                  : "PER_ZONE",
              opensAt: toLocalInput(s.opensAt),
              closesAt: toLocalInput(s.closesAt),
              quotaByZone: formatQuotaByZone(s.quotaByZone),
              quota: s.quota == null ? "" : String(s.quota),
              minScore: s.minScore == null ? "" : String(s.minScore),
              exerciseStatus: s.exerciseStatus ?? null,
            })),
          );
          setFinalists(pathway.finalistsPerSkill);
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
  }, [competitionId, skillId]);

  function updateStage(index: number, patch: Partial<StageDraft>) {
    setStages((prev) =>
      prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    );
  }

  function addStage() {
    setStages((prev) => [...prev, emptyStage(prev.length + 1)]);
  }

  function removeStage(index: number) {
    setStages((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== index);
    });
  }

  function moveStage(index: number, direction: -1 | 1) {
    setStages((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function setZoneQuota(index: number, zoneId: string, amount: string) {
    const stage = stages[index];
    const current = parseQuotaText(stage.quotaByZone) || {};
    const n = amount.trim() === "" ? undefined : Number(amount);
    if (n === undefined || Number.isNaN(n)) {
      delete current[zoneId];
    } else {
      current[zoneId] = n;
    }
    updateStage(index, { quotaByZone: formatQuotaByZone(current) });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    setPending(true);
    try {
      const payload: StagePathwayItem[] = [];
      for (let i = 0; i < stages.length; i++) {
        const s = stages[i];
        if (s.type !== "VIRTUAL" && s.type !== "PHYSICAL") {
          setFieldErrors({ [`stages.${i}.type`]: "INVALID_TYPE" });
          setPending(false);
          return;
        }
        const minRaw = s.minScore.trim();
        const opensIso = fromLocalInput(s.opensAt);
        const closesIso = fromLocalInput(s.closesAt);
        if (s.opensAt.trim() && !opensIso) {
          setFieldErrors({
            [`stages.${i}.opensAt`]: "Enter a valid date and time.",
          });
          setPending(false);
          return;
        }
        if (s.closesAt.trim() && !closesIso) {
          setFieldErrors({
            [`stages.${i}.closesAt`]: "Enter a valid date and time.",
          });
          setPending(false);
          return;
        }
        if (opensIso && closesIso && new Date(closesIso) <= new Date(opensIso)) {
          setFieldErrors({
            [`stages.${i}.closesAt`]:
              "Submission deadline must be after Available from.",
          });
          setPending(false);
          return;
        }
        const windowFields = {
          opensAt: opensIso,
          closesAt: closesIso,
        };
        if (s.selectionMode === "NATIONAL_POOL") {
          const quotaNum = Number(s.quota.trim());
          if (s.quota.trim() === "" || Number.isNaN(quotaNum) || quotaNum < 0) {
            setFieldErrors({
              [`stages.${i}.quota`]: "Overall quota must be an integer ≥ 0.",
            });
            setPending(false);
            return;
          }
          payload.push({
            order: i + 1,
            type: s.type,
            selectionMode: "NATIONAL_POOL",
            quota: quotaNum,
            minScore: minRaw === "" ? null : Number(minRaw),
            ...windowFields,
          });
        } else {
          const quota = parseQuotaText(s.quotaByZone);
          if (!quota) {
            setFieldErrors({
              [`stages.${i}.quotaByZone`]:
                "Set at least one per-zone quota (zone pickers below).",
            });
            setPending(false);
            return;
          }
          payload.push({
            order: i + 1,
            type: s.type,
            selectionMode: "PER_ZONE",
            quotaByZone: quota,
            minScore: minRaw === "" ? null : Number(minRaw),
            ...windowFields,
          });
        }
      }
      const result = await putPathway(competitionId, skillId, payload);
      setFinalists(result.finalistsPerSkill);
      setStages(
        result.stages.map((s) => ({
          stageId: s.stageId,
          order: String(s.order),
          type: s.type,
          selectionMode:
            s.selectionMode === "NATIONAL_POOL" ? "NATIONAL_POOL" : "PER_ZONE",
          opensAt: toLocalInput(s.opensAt),
          closesAt: toLocalInput(s.closesAt),
          quotaByZone: formatQuotaByZone(s.quotaByZone),
          quota: s.quota == null ? "" : String(s.quota),
          minScore: s.minScore == null ? "" : String(s.minScore),
          exerciseStatus: s.exerciseStatus ?? null,
        })),
      );
      setSavedMessage("Pathway saved");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not save pathway",
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

  const exerciseStage =
    exerciseStageIndex != null ? stages[exerciseStageIndex] : null;

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title="Stage pathway"
        description="Ordered stages with windows, quotas, and thresholds. Configure each stage’s exercise after saving."
        backHref={`/admin/competitions/${competitionId}/skills/${skillId}`}
        backLabel="Skill"
      />

      <ApiErrorAlert error={error} />

      <div
        className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border pb-6"
        data-testid="finalists-summary"
      >
        <div>
          <p className="text-sm text-muted-foreground">Finalists per skill</p>
          <p className="text-2xl font-semibold tabular-nums tracking-tight">
            {finalists == null ? "—" : finalists}
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          Computed from saved stage quotas.
        </p>
      </div>

      {loading ? (
        <div className="space-y-4" role="status" aria-label="Loading pathway">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <form
          onSubmit={onSubmit}
          className="space-y-0"
          noValidate
          data-testid="pathway-editor"
        >
          {stages.map((stage, index) => {
            const quotaMap = parseQuotaText(stage.quotaByZone) || {};
            return (
              <section key={stage.stageId ?? `draft-${index}`}>
                {index > 0 ? <Separator className="my-8" /> : null}

                <div className="space-y-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="flex size-8 items-center justify-center rounded-full bg-muted text-sm font-semibold tabular-nums text-foreground">
                          {index + 1}
                        </span>
                        <h2 className="text-lg font-semibold tracking-tight">
                          Stage {index + 1}
                        </h2>
                        <Badge
                          variant={exerciseBadgeVariant(stage.exerciseStatus)}
                        >
                          {exerciseStatusLabel(stage.exerciseStatus)}
                        </Badge>
                      </div>
                      {index === 0 ? (
                        <p className="max-w-2xl text-sm text-muted-foreground">
                          Stage 1 admits all registered competitors. Quota
                          below is how many advance after assessment — not a
                          registration limit.
                        </p>
                      ) : null}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {stage.stageId ? (
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="min-h-9"
                          onClick={() => setExerciseStageIndex(index)}
                        >
                          Edit exercise
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          Save pathway to configure exercise
                        </span>
                      )}
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="min-h-9 min-w-9"
                        disabled={index === 0}
                        onClick={() => moveStage(index, -1)}
                        aria-label={`Move stage ${index + 1} up`}
                      >
                        <ArrowUpIcon className="size-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="min-h-9 min-w-9"
                        disabled={index === stages.length - 1}
                        onClick={() => moveStage(index, 1)}
                        aria-label={`Move stage ${index + 1} down`}
                      >
                        <ArrowDownIcon className="size-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="min-h-9 min-w-9"
                        disabled={stages.length <= 1}
                        onClick={() => removeStage(index)}
                        aria-label={`Remove stage ${index + 1}`}
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    </div>
                  </div>

                  <div className="grid gap-5 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Stage type</Label>
                      <Select
                        value={stage.type || undefined}
                        onValueChange={(v) =>
                          updateStage(index, { type: v ?? "VIRTUAL" })
                        }
                      >
                        <SelectTrigger className="min-h-11 w-full">
                          <SelectValue placeholder="VIRTUAL or PHYSICAL" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="VIRTUAL">Virtual</SelectItem>
                          <SelectItem value="PHYSICAL">Physical</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldMessage
                        message={fieldErrors[`stages.${index}.type`]}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Selection mode</Label>
                      <Select
                        value={stage.selectionMode}
                        onValueChange={(v) =>
                          updateStage(index, {
                            selectionMode:
                              v === "NATIONAL_POOL"
                                ? "NATIONAL_POOL"
                                : "PER_ZONE",
                          })
                        }
                      >
                        <SelectTrigger
                          className="min-h-11 w-full"
                          data-testid={`stage-${index}-selectionMode`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="PER_ZONE">Per zone</SelectItem>
                          <SelectItem value="NATIONAL_POOL">
                            National pool
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldMessage
                        message={
                          fieldErrors[`stages.${index}.selectionMode`]
                        }
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor={`stage-${index}-opensAt`}>
                        Available from
                      </Label>
                      <Input
                        id={`stage-${index}-opensAt`}
                        type="datetime-local"
                        className="min-h-11"
                        value={stage.opensAt}
                        onChange={(e) =>
                          updateStage(index, { opensAt: e.target.value })
                        }
                        data-testid={`stage-${index}-opensAt`}
                      />
                      <FieldMessage
                        message={fieldErrors[`stages.${index}.opensAt`]}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor={`stage-${index}-closesAt`}>
                        Submission deadline
                      </Label>
                      <Input
                        id={`stage-${index}-closesAt`}
                        type="datetime-local"
                        className="min-h-11"
                        value={stage.closesAt}
                        onChange={(e) =>
                          updateStage(index, { closesAt: e.target.value })
                        }
                        data-testid={`stage-${index}-closesAt`}
                      />
                      <FieldMessage
                        message={fieldErrors[`stages.${index}.closesAt`]}
                      />
                    </div>

                    {stage.selectionMode === "NATIONAL_POOL" ? (
                      <div className="space-y-2 sm:col-span-2">
                        <Label htmlFor={`stage-${index}-quota`}>
                          Overall national quota
                        </Label>
                        <Input
                          id={`stage-${index}-quota`}
                          inputMode="numeric"
                          className="min-h-11 max-w-xs"
                          value={stage.quota}
                          placeholder="10"
                          onChange={(e) =>
                            updateStage(index, { quota: e.target.value })
                          }
                        />
                        <FieldMessage
                          message={fieldErrors[`stages.${index}.quota`]}
                        />
                      </div>
                    ) : (
                      <div className="space-y-3 sm:col-span-2">
                        <Label>Quota by zone</Label>
                        {zones.length === 0 ? (
                          <p className="text-sm text-muted-foreground">
                            No zones configured.{" "}
                            <Link
                              href={`/admin/competitions/${competitionId}/zones`}
                              className="underline underline-offset-2"
                            >
                              Configure zones
                            </Link>{" "}
                            first, or paste zoneId:n lines below.
                          </p>
                        ) : (
                          <div className="divide-y divide-border rounded-xl ring-1 ring-foreground/10">
                            {zones.map((z) => (
                              <div
                                key={z.zoneId}
                                className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_8rem] sm:items-center"
                              >
                                <span className="text-sm">{z.name}</span>
                                <Input
                                  inputMode="numeric"
                                  className="min-h-11"
                                  value={
                                    quotaMap[z.zoneId] == null
                                      ? ""
                                      : String(quotaMap[z.zoneId])
                                  }
                                  placeholder="0"
                                  onChange={(e) =>
                                    setZoneQuota(
                                      index,
                                      z.zoneId,
                                      e.target.value,
                                    )
                                  }
                                />
                              </div>
                            ))}
                          </div>
                        )}
                        <Input
                          id={`stage-${index}-quotaByZone`}
                          value={stage.quotaByZone}
                          placeholder="zone-uuid:10 (advanced)"
                          className="font-mono text-xs"
                          onChange={(e) =>
                            updateStage(index, {
                              quotaByZone: e.target.value,
                            })
                          }
                        />
                        <FieldMessage
                          message={
                            fieldErrors[`stages.${index}.quotaByZone`]
                          }
                        />
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label htmlFor={`stage-${index}-minScore`}>
                        Minimum score (optional)
                      </Label>
                      <Input
                        id={`stage-${index}-minScore`}
                        inputMode="numeric"
                        className="min-h-11"
                        value={stage.minScore}
                        onChange={(e) =>
                          updateStage(index, { minScore: e.target.value })
                        }
                      />
                    </div>
                  </div>
                </div>
              </section>
            );
          })}

          <Separator className="my-8" />

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={addStage}
            >
              <PlusIcon className="size-4" />
              Add stage
            </Button>
            <Button
              type="submit"
              className="min-h-11"
              disabled={pending || loading}
            >
              {pending ? "Saving…" : "Save pathway"}
            </Button>
          </div>

          {savedMessage ? (
            <Alert className="mt-6">
              <AlertTitle>Saved</AlertTitle>
              <AlertDescription>{savedMessage}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      )}

      <StageExerciseDialog
        open={exerciseStageIndex != null && Boolean(exerciseStage?.stageId)}
        onOpenChange={(open) => {
          if (!open) setExerciseStageIndex(null);
        }}
        competitionId={competitionId}
        stageId={exerciseStage?.stageId ?? ""}
        stageLabel={
          exerciseStageIndex != null
            ? `Stage ${exerciseStageIndex + 1}`
            : undefined
        }
        onStatusChange={(status) => {
          if (exerciseStageIndex == null) return;
          updateStage(exerciseStageIndex, { exerciseStatus: status });
        }}
      />
    </PageShell>
  );
}
