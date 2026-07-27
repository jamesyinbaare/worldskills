"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AgeRuleOut,
  ApiError,
  createAgeRule,
  createPathway,
  createSkill,
  listAgeRules,
  listPathways,
  PathwayConfigOut,
} from "@/lib/api";
import {
  AgeRuleCreateDialog,
  ConfigEntityField,
  NameCreateDialog,
} from "@/components/admin/ConfigEntityField";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function ageRuleLabel(rule: AgeRuleOut): string {
  const parts = [rule.name, `max ${rule.maxAge}`];
  if (rule.referenceDate) parts.push(`ref ${rule.referenceDate}`);
  return parts.join(" · ");
}

export default function NewSkillPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const competitionId = params.id;

  const [name, setName] = useState("");
  const [number, setNumber] = useState("");
  const [familyId, setFamilyId] = useState("");
  const [ageRuleId, setAgeRuleId] = useState("");
  const [pathwayId, setPathwayId] = useState("");
  const [capacity, setCapacity] = useState("");

  const [ageRules, setAgeRules] = useState<AgeRuleOut[]>([]);
  const [pathways, setPathways] = useState<PathwayConfigOut[]>([]);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState<ApiError | null>(null);

  const [ageDialogOpen, setAgeDialogOpen] = useState(false);
  const [pathwayDialogOpen, setPathwayDialogOpen] = useState(false);

  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setOptionsLoading(true);
      setOptionsError(null);
      try {
        const [ages, paths] = await Promise.all([
          listAgeRules(competitionId),
          listPathways(competitionId),
        ]);
        if (!cancelled) {
          setAgeRules(ages);
          setPathways(paths);
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setOptionsError(err);
      } finally {
        if (!cancelled) setOptionsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const capacityValue = capacity.trim() === "" ? null : Number(capacity);
      await createSkill(competitionId, {
        name: name.trim(),
        number: emptyToNull(number),
        familyId: emptyToNull(familyId),
        ageRuleId: emptyToNull(ageRuleId),
        pathwayId: emptyToNull(pathwayId),
        capacity: capacityValue,
      });
      router.push(`/admin/competitions/${competitionId}/skills`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not create skill",
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
    <PageShell width="narrow">
      <PageHeader
        title="Create skill"
        description="Link eligibility, pathway and capacity so registration can resolve per skill."
        backHref={`/admin/competitions/${competitionId}/skills`}
        backLabel="Skills"
      />

      <Card>
        <CardHeader>
          <CardDescription>
            Attach eligibility and pathway config for this skill. Marking
            schemes are configured on each stage exercise.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ApiErrorAlert error={optionsError} className="mb-4" />
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                required
                maxLength={120}
                value={name}
                aria-invalid={Boolean(fieldErrors.name)}
                aria-describedby={fieldErrors.name ? "name-error" : undefined}
                onChange={(e) => setName(e.target.value)}
              />
              <FieldMessage id="name-error" message={fieldErrors.name} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="number">Number (optional)</Label>
              <Input
                id="number"
                maxLength={32}
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="familyId">Family (optional)</Label>
              <Input
                id="familyId"
                value={familyId}
                onChange={(e) => setFamilyId(e.target.value)}
                placeholder="e.g. IT"
              />
            </div>

            <ConfigEntityField
              id="ageRuleId"
              label="Age rule"
              value={ageRuleId}
              options={ageRules.map((r) => ({
                id: r.ageRuleId,
                label: ageRuleLabel(r),
              }))}
              loading={optionsLoading}
              error={fieldErrors.ageRuleId}
              emptyTitle="No age rules yet"
              emptyDescription="Create an age rule to set eligibility limits for this skill."
              createLabel="Create age rule"
              onValueChange={setAgeRuleId}
              onCreate={() => setAgeDialogOpen(true)}
            />

            <ConfigEntityField
              id="pathwayId"
              label="Pathway"
              value={pathwayId}
              options={pathways.map((p) => ({
                id: p.pathwayId,
                label: p.name,
              }))}
              loading={optionsLoading}
              error={fieldErrors.pathwayId}
              emptyTitle="No pathways yet"
              emptyDescription="Create a named pathway stub to attach to this skill. Stages are configured after the skill exists."
              createLabel="Create pathway"
              onValueChange={setPathwayId}
              onCreate={() => setPathwayDialogOpen(true)}
            />

            <div className="space-y-2">
              <Label htmlFor="capacity">Capacity (optional)</Label>
              <Input
                id="capacity"
                type="number"
                min={1}
                value={capacity}
                aria-invalid={Boolean(fieldErrors.capacity)}
                aria-describedby={
                  fieldErrors.capacity ? "capacity-error" : undefined
                }
                onChange={(e) => setCapacity(e.target.value)}
              />
              <FieldMessage
                id="capacity-error"
                message={fieldErrors.capacity}
              />
            </div>
            <ApiErrorAlert error={error} />
            <Button type="submit" disabled={pending} className="min-h-11">
              {pending ? "Saving…" : "Save skill"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <AgeRuleCreateDialog
        open={ageDialogOpen}
        onOpenChange={setAgeDialogOpen}
        onSubmit={async (payload) => {
          const created = await createAgeRule(competitionId, payload);
          setAgeRules((prev) =>
            [...prev, created].sort((a, b) => a.name.localeCompare(b.name)),
          );
          setAgeRuleId(created.ageRuleId);
        }}
      />

      <NameCreateDialog
        open={pathwayDialogOpen}
        onOpenChange={setPathwayDialogOpen}
        title="Create pathway"
        description="Name a pathway stub for this competition. Configure stages from the skill pathway editor after creating the skill."
        submitLabel="Create pathway"
        onSubmit={async (pathwayName) => {
          const created = await createPathway(competitionId, { name: pathwayName });
          setPathways((prev) =>
            [...prev, created].sort((a, b) => a.name.localeCompare(b.name)),
          );
          setPathwayId(created.pathwayId);
        }}
      />
    </PageShell>
  );
}
