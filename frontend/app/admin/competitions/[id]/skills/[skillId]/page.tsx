"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  AssignmentOut,
  SkillOut,
  UserOut,
  ZoneOut,
  createAssignment,
  deleteSkillCriteriaDocument,
  downloadSkillCriteriaDocument,
  listAssignments,
  listCycleZones,
  listSkills,
  listUsers,
  patchCatalogSkill,
  patchCycleSkill,
  triggerBrowserDownload,
  uploadSkillCriteriaDocument,
} from "@/lib/api";
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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function CycleSkillDetailPage() {
  const params = useParams<{ id: string; skillId: string }>();
  const competitionId = params.id;
  const skillId = params.skillId;

  const [skill, setSkill] = useState<SkillOut | null>(null);
  const [assignments, setAssignments] = useState<AssignmentOut[]>([]);
  const [experts, setExperts] = useState<UserOut[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const [maxAge, setMaxAge] = useState("");
  const [referenceDate, setReferenceDate] = useState("");
  const [openCategory, setOpenCategory] = useState(false);
  const [capacity, setCapacity] = useState("");
  const [skillSaveError, setSkillSaveError] = useState<ApiError | null>(null);
  const [skillFieldErrors, setSkillFieldErrors] = useState<
    Record<string, string>
  >({});
  const [skillPending, setSkillPending] = useState(false);
  const [skillSaved, setSkillSaved] = useState<string | null>(null);

  const [description, setDescription] = useState("");
  const [descPending, setDescPending] = useState(false);
  const [descError, setDescError] = useState<ApiError | null>(null);
  const [descSaved, setDescSaved] = useState<string | null>(null);

  const [criteriaPending, setCriteriaPending] = useState(false);
  const [criteriaError, setCriteriaError] = useState<ApiError | null>(null);
  const [criteriaMessage, setCriteriaMessage] = useState<string | null>(null);
  const criteriaInputRef = useRef<HTMLInputElement>(null);

  const [expertId, setExpertId] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [zones, setZones] = useState<ZoneOut[]>([]);
  const [assignError, setAssignError] = useState<ApiError | null>(null);
  const [assignFieldErrors, setAssignFieldErrors] = useState<
    Record<string, string>
  >({});
  const [assignPending, setAssignPending] = useState(false);
  const [assignCreated, setAssignCreated] = useState<AssignmentOut | null>(
    null,
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [skills, assigns, expertList, cycleZones] = await Promise.all([
        listSkills(competitionId),
        listAssignments(competitionId, { cycleSkillId: skillId }),
        listUsers({ role: "EXPERT,CHIEF_EXPERT", active: true }),
        listCycleZones(competitionId),
      ]);
      const found = skills.find((s) => s.skillId === skillId) ?? null;
      setSkill(found);
      setAssignments(assigns);
      setExperts(expertList);
      setZones(cycleZones.filter((z) => z.active));
      if (found?.ageRule) {
        setMaxAge(String(found.ageRule.maxAge));
        setReferenceDate(found.ageRule.referenceDate ?? "");
        setOpenCategory(found.ageRule.openCategoryEnabled);
      }
      setCapacity(found?.capacity != null ? String(found.capacity) : "");
      setDescription(found?.description ?? "");
    } catch (err) {
      if (err instanceof ApiError) setLoadError(err);
    } finally {
      setLoading(false);
    }
  }, [competitionId, skillId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  async function onSaveSkill(e: FormEvent) {
    e.preventDefault();
    setSkillSaveError(null);
    setSkillFieldErrors({});
    setSkillSaved(null);
    setSkillPending(true);
    try {
      const capRaw = capacity.trim();
      const updated = await patchCycleSkill(competitionId, skillId, {
        ageRule: {
          maxAge: Number(maxAge),
          referenceDate: referenceDate.trim() || null,
          openCategoryEnabled: openCategory,
        },
        capacity: capRaw === "" ? null : Number(capRaw),
      });
      setSkill(updated);
      setSkillSaved("Skill settings saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setSkillSaveError(err);
        setSkillFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setSkillPending(false);
    }
  }

  async function onSaveDescription(e: FormEvent) {
    e.preventDefault();
    if (!skill?.catalogSkillId) return;
    setDescError(null);
    setDescSaved(null);
    setDescPending(true);
    try {
      const updated = await patchCatalogSkill(skill.catalogSkillId, {
        description: description.trim() || null,
      });
      setDescription(updated.description ?? "");
      setSkill((prev) =>
        prev
          ? { ...prev, description: updated.description ?? null }
          : prev,
      );
      setDescSaved("Public description saved.");
    } catch (err) {
      if (err instanceof ApiError) setDescError(err);
    } finally {
      setDescPending(false);
    }
  }

  async function onAssignExpert(e: FormEvent) {
    e.preventDefault();
    setAssignError(null);
    setAssignFieldErrors({});
    setAssignCreated(null);
    setAssignPending(true);
    try {
      const out = await createAssignment(competitionId, {
        expertId: expertId.trim(),
        cycleSkillId: skillId,
        zoneId: zoneId.trim(),
      });
      setAssignCreated(out);
      setExpertId("");
      setZoneId("");
      const assigns = await listAssignments(competitionId, { cycleSkillId: skillId });
      setAssignments(assigns);
    } catch (err) {
      if (err instanceof ApiError) {
        setAssignError(err);
        setAssignFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setAssignPending(false);
    }
  }

  const expertName = (id: string) =>
    experts.find((e) => e.userId === id)?.fullName ?? id;

  if (loading) {
    return (
      <PageShell className="space-y-6">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </PageShell>
    );
  }

  if (loadError) {
    return (
      <PageShell>
        <PageHeader
          title="Skill"
          backHref={`/admin/competitions/${competitionId}/skills`}
          backLabel="Skills"
        />
        <ApiErrorAlert error={loadError} />
      </PageShell>
    );
  }

  if (!skill) {
    return (
      <PageShell>
        <PageHeader
          title="Skill not found"
          backHref={`/admin/competitions/${competitionId}/skills`}
          backLabel="Skills"
        />
        <p className="text-sm text-muted-foreground">
          This skill is not associated with the competition.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell className="space-y-8">
      <PageHeader
        title={skill.name}
        description={
          [
            skill.familyName,
            skill.number ? `#${skill.number}` : null,
            skill.hasPathway ? "Pathway configured" : "Pathway not set",
          ]
            .filter(Boolean)
            .join(" · ") || "Competition skill configuration"
        }
        backHref={`/admin/competitions/${competitionId}/skills`}
        backLabel="Skills"
        actions={
          <Button variant="outline" className="min-h-11" asChild>
            <Link
              href={`/admin/competitions/${competitionId}/skills/${skillId}/pathway`}
            >
              Stage pathway
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Public description</CardTitle>
          <CardDescription>
            Multi-line about text shown on the public skill area page. Shared
            across competitions that use this catalog skill.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {skill.catalogSkillId ? (
            <form onSubmit={onSaveDescription} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="skillDescription">About this skill area</Label>
                <Textarea
                  id="skillDescription"
                  className="min-h-40"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={20000}
                  placeholder="Describe this skill area for competitors and institutions…"
                  data-testid="cycle-skill-description"
                />
              </div>
              <ApiErrorAlert error={descError} title="Could not save description" />
              {descSaved ? (
                <p className="text-sm text-muted-foreground" role="status">
                  {descSaved}
                </p>
              ) : null}
              <Button
                type="submit"
                disabled={descPending}
                className="min-h-11"
                data-testid="cycle-skill-description-save"
              >
                {descPending ? "Saving…" : "Save description"}
              </Button>
            </form>
          ) : (
            <p className="text-sm text-muted-foreground">
              This skill is not linked to the catalog, so a public description
              cannot be edited here. Associate a catalog skill or edit skills
              under{" "}
              <Link href="/admin/skills" className="font-medium underline">
                Skills catalog
              </Link>
              .
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Age rule and capacity</CardTitle>
          <CardDescription>
            One age rule per skill for this competition. Capacity limits registrations
            when set.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSaveSkill} className="space-y-4" noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="maxAge">Maximum age</Label>
                <Input
                  id="maxAge"
                  inputMode="numeric"
                  className="min-h-11"
                  value={maxAge}
                  onChange={(e) => setMaxAge(e.target.value)}
                  required
                />
                <FieldMessage message={skillFieldErrors["ageRule.maxAge"]} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="referenceDate">Reference date (optional)</Label>
                <Input
                  id="referenceDate"
                  type="date"
                  className="min-h-11"
                  value={referenceDate}
                  onChange={(e) => setReferenceDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="capacity">Capacity (optional)</Label>
                <Input
                  id="capacity"
                  inputMode="numeric"
                  className="min-h-11"
                  value={capacity}
                  onChange={(e) => setCapacity(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="openCategory">Open category</Label>
                <Select
                  value={openCategory ? "yes" : "no"}
                  onValueChange={(v) => setOpenCategory(v === "yes")}
                >
                  <SelectTrigger id="openCategory" className="min-h-11 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="no">No</SelectItem>
                    <SelectItem value="yes">Yes</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <ApiErrorAlert error={skillSaveError} title="Could not save skill" />
            <Button type="submit" className="min-h-11" disabled={skillPending}>
              {skillPending ? "Saving…" : "Save skill settings"}
            </Button>
            {skillSaved ? (
              <Alert>
                <AlertTitle>Saved</AlertTitle>
                <AlertDescription>{skillSaved}</AlertDescription>
              </Alert>
            ) : null}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Skill-area criteria</CardTitle>
          <CardDescription>
            Upload the criteria document for this skill. Competitors and
            institutions can view and download it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Document</dt>
              <dd className="font-medium">
                {skill.criteriaFileName ?? "None uploaded"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Scan status</dt>
              <dd>
                {skill.criteriaScanStatus ? (
                  <Badge variant="secondary">{skill.criteriaScanStatus}</Badge>
                ) : (
                  "—"
                )}
              </dd>
            </div>
          </dl>
          <input
            ref={criteriaInputRef}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0] ?? null;
              if (!file) return;
              void (async () => {
                setCriteriaPending(true);
                setCriteriaError(null);
                setCriteriaMessage(null);
                try {
                  const updated = await uploadSkillCriteriaDocument(
                    competitionId,
                    skillId,
                    file,
                  );
                  setSkill(updated);
                  setCriteriaMessage("Criteria document uploaded.");
                } catch (err) {
                  if (err instanceof ApiError) setCriteriaError(err);
                } finally {
                  setCriteriaPending(false);
                  if (criteriaInputRef.current) {
                    criteriaInputRef.current.value = "";
                  }
                }
              })();
            }}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={criteriaPending}
              onClick={() => criteriaInputRef.current?.click()}
              data-testid="skill-criteria-upload"
            >
              {criteriaPending
                ? "Working…"
                : skill.hasCriteriaDocument
                  ? "Replace document"
                  : "Upload document"}
            </Button>
            {skill.hasCriteriaDocument ? (
              <>
                <Button
                  type="button"
                  variant="secondary"
                  className="min-h-11"
                  disabled={criteriaPending}
                  onClick={() => {
                    void (async () => {
                      setCriteriaPending(true);
                      setCriteriaError(null);
                      try {
                        const { blob, filename } =
                          await downloadSkillCriteriaDocument(
                            competitionId,
                            skillId,
                          );
                        triggerBrowserDownload(blob, filename);
                      } catch (err) {
                        if (err instanceof ApiError) setCriteriaError(err);
                      } finally {
                        setCriteriaPending(false);
                      }
                    })();
                  }}
                >
                  Download
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11"
                  disabled={criteriaPending}
                  onClick={() => {
                    void (async () => {
                      setCriteriaPending(true);
                      setCriteriaError(null);
                      setCriteriaMessage(null);
                      try {
                        const updated = await deleteSkillCriteriaDocument(
                          competitionId,
                          skillId,
                        );
                        setSkill(updated);
                        setCriteriaMessage("Criteria document removed.");
                      } catch (err) {
                        if (err instanceof ApiError) setCriteriaError(err);
                      } finally {
                        setCriteriaPending(false);
                      }
                    })();
                  }}
                >
                  Remove
                </Button>
              </>
            ) : null}
          </div>
          <ApiErrorAlert error={criteriaError} title="Criteria document" />
          {criteriaMessage ? (
            <Alert>
              <AlertTitle>Updated</AlertTitle>
              <AlertDescription>{criteriaMessage}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Expert assignments</CardTitle>
          <CardDescription>
            Assign experts to this skill and zone. Conflict-of-interest flags are
            returned when detected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {assignments.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No experts assigned yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Expert</TableHead>
                  <TableHead>Zone</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignments.map((a) => (
                  <TableRow key={a.assignmentId}>
                    <TableCell>{expertName(a.expertId)}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {a.zoneId}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          <Separator />

          <form onSubmit={onAssignExpert} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="expertId">Expert</Label>
              <Select value={expertId} onValueChange={setExpertId}>
                <SelectTrigger id="expertId" className="min-h-11 w-full">
                  <SelectValue placeholder="Select expert" />
                </SelectTrigger>
                <SelectContent>
                  {experts.map((ex) => (
                    <SelectItem key={ex.userId} value={ex.userId}>
                      {ex.fullName} ({ex.email})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldMessage message={assignFieldErrors.expertId} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="zoneId">Zone</Label>
              <Select value={zoneId} onValueChange={setZoneId}>
                <SelectTrigger id="zoneId" className="min-h-11 w-full">
                  <SelectValue placeholder="Select zone" />
                </SelectTrigger>
                <SelectContent>
                  {zones.map((z) => (
                    <SelectItem key={z.zoneId} value={z.zoneId}>
                      {z.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {zones.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No zones yet.{" "}
                  <Link
                    href={`/admin/competitions/${competitionId}/zones`}
                    className="underline underline-offset-2"
                  >
                    Configure zones
                  </Link>
                  .
                </p>
              ) : null}
              <FieldMessage message={assignFieldErrors.zoneId} />
            </div>
            <ApiErrorAlert error={assignError} title="Could not assign expert" />
            <Button type="submit" className="min-h-11" disabled={assignPending}>
              {assignPending ? "Assigning…" : "Assign expert"}
            </Button>
          </form>

          {assignCreated ? (
            <Alert data-testid="assignment-result">
              <AlertTitle>Assignment created</AlertTitle>
              <AlertDescription className="space-y-2">
                {assignCreated.coiFlags.length === 0 ? (
                  <p className="text-sm">No conflict-of-interest flags.</p>
                ) : (
                  <ul className="space-y-2">
                    {assignCreated.coiFlags.map((flag) => (
                      <li
                        key={`${flag.institutionId}-${flag.reason}`}
                        className="flex flex-wrap items-center gap-2"
                      >
                        <Badge variant="secondary">{flag.reason}</Badge>
                        <span className="text-sm break-all">
                          Institution {flag.institutionId}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>
    </PageShell>
  );
}
