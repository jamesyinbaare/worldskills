"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  CatalogSkillOut,
  SkillOut,
  associateSkill,
  listCatalogSkills,
  listSkills,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

export default function AssociateSkillPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const competitionId = params.id;

  const [catalog, setCatalog] = useState<CatalogSkillOut[]>([]);
  const [associated, setAssociated] = useState<SkillOut[]>([]);
  const [skillId, setSkillId] = useState("");
  const [maxAge, setMaxAge] = useState("25");
  const [referenceDate, setReferenceDate] = useState("");
  const [openCategory, setOpenCategory] = useState(false);
  const [capacity, setCapacity] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cat, cycleSkills] = await Promise.all([
          listCatalogSkills({ active: true }),
          listSkills(competitionId),
        ]);
        if (!cancelled) {
          setCatalog(cat);
          setAssociated(cycleSkills);
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
  }, [competitionId]);

  const available = useMemo(() => {
    const taken = new Set(
      associated.map((s) => s.catalogSkillId).filter(Boolean) as string[],
    );
    return catalog.filter((s) => !taken.has(s.skillId));
  }, [catalog, associated]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const max = Number(maxAge);
      if (!skillId) {
        setFieldErrors({ skillId: "REQUIRED" });
        setPending(false);
        return;
      }
      if (!Number.isFinite(max) || max < 0) {
        setFieldErrors({ "ageRule.maxAge": "INVALID" });
        setPending(false);
        return;
      }
      await associateSkill(competitionId, {
        skillId,
        ageRule: {
          maxAge: max,
          referenceDate: referenceDate.trim() || null,
          openCategoryEnabled: openCategory,
        },
        capacity: capacity.trim() ? Number(capacity) : null,
      });
      router.push(`/admin/competitions/${competitionId}/skills`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Associate skill"
        description="Pick a catalog skill and define this competition’s age rule and capacity."
        backHref={`/admin/competitions/${competitionId}/skills`}
        backLabel="Competition skills"
      />

      <ApiErrorAlert error={error} className="mb-6" />

      <Card>
        <CardHeader>
          <CardDescription>
            {loading
              ? "Loading catalog…"
              : available.length === 0
                ? "All active catalog skills are already on this competition (or the catalog is empty)."
                : "Select a skill from the global catalog."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label>Catalog skill</Label>
              <Select value={skillId || undefined} onValueChange={setSkillId}>
                <SelectTrigger className="min-h-11 w-full">
                  <SelectValue placeholder="Select skill" />
                </SelectTrigger>
                <SelectContent>
                  {available.map((s) => (
                    <SelectItem key={s.skillId} value={s.skillId}>
                      {s.familyName ? `${s.familyName} · ` : ""}
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldMessage message={fieldErrors.skillId} />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="max-age">Max age</Label>
                <Input
                  id="max-age"
                  type="number"
                  min={0}
                  value={maxAge}
                  onChange={(e) => setMaxAge(e.target.value)}
                  required
                  className="min-h-11"
                />
                <FieldMessage
                  message={
                    fieldErrors["ageRule.maxAge"] || fieldErrors.maxAge
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ref-date">Reference date</Label>
                <Input
                  id="ref-date"
                  type="date"
                  value={referenceDate}
                  onChange={(e) => setReferenceDate(e.target.value)}
                  className="min-h-11"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={openCategory}
                onChange={(e) => setOpenCategory(e.target.checked)}
              />
              Open category enabled (over-age demonstration track)
            </label>

            <div className="space-y-2">
              <Label htmlFor="capacity">Capacity (optional)</Label>
              <Input
                id="capacity"
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                className="min-h-11"
              />
              <FieldMessage message={fieldErrors.capacity} />
            </div>

            <Button
              type="submit"
              disabled={pending || available.length === 0}
              className="min-h-11"
            >
              {pending ? "Associating…" : "Associate skill"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
