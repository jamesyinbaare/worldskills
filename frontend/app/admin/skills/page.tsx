"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  CatalogSkillOut,
  FamilyOut,
  createCatalogSkill,
  listCatalogSkills,
  listFamilies,
  patchCatalogSkill,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

type SkillFormState = {
  name: string;
  number: string;
  description: string;
  familyId: string;
};

const emptyForm = (): SkillFormState => ({
  name: "",
  number: "",
  description: "",
  familyId: "",
});

function formFromSkill(skill: CatalogSkillOut): SkillFormState {
  return {
    name: skill.name,
    number: skill.number ?? "",
    description: skill.description ?? "",
    familyId: skill.familyId,
  };
}

export default function AdminSkillsCatalogPage() {
  const [skills, setSkills] = useState<CatalogSkillOut[]>([]);
  const [families, setFamilies] = useState<FamilyOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<SkillFormState>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [sk, fam] = await Promise.all([listCatalogSkills(), listFamilies()]);
      setSkills(sk);
      setFamilies(fam.filter((f) => f.active));
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function startCreate() {
    setEditingId(null);
    setForm(emptyForm());
    setFieldErrors({});
    setError(null);
    setSavedMessage(null);
  }

  function startEdit(skill: CatalogSkillOut) {
    setEditingId(skill.skillId);
    setForm(formFromSkill(skill));
    setFieldErrors({});
    setError(null);
    setSavedMessage(null);
    document.getElementById("skill-form")?.scrollIntoView({ behavior: "smooth" });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    try {
      if (!form.familyId) {
        setFieldErrors({ familyId: "REQUIRED" });
        setPending(false);
        return;
      }
      const payload = {
        name: form.name.trim(),
        number: form.number.trim() || null,
        familyId: form.familyId,
        description: form.description.trim() || null,
      };
      if (editingId) {
        const updated = await patchCatalogSkill(editingId, payload);
        setForm(formFromSkill(updated));
        setSavedMessage("Skill updated.");
      } else {
        await createCatalogSkill(payload);
        setSavedMessage("Skill created.");
        setForm(emptyForm());
      }
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  async function toggleActive(skill: CatalogSkillOut) {
    setError(null);
    try {
      await patchCatalogSkill(skill.skillId, { active: !skill.active });
      await load();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }

  const familyOptions: FamilyOut[] = (() => {
    const byId = new Map(families.map((f) => [f.familyId, f]));
    if (form.familyId && !byId.has(form.familyId)) {
      const editing = skills.find((s) => s.skillId === editingId);
      if (editing) {
        byId.set(editing.familyId, {
          familyId: editing.familyId,
          name: editing.familyName || "Current family",
          active: true,
        });
      }
    }
    return Array.from(byId.values());
  })();

  return (
    <PageShell width="wide" className="max-w-5xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel mb-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Skills catalog"
          description="Global skills reused across cycles. Edit the multi-line description to show on public skill area pages."
          actions={
            <Button variant="outline" className="min-h-11" asChild>
              <Link href="/admin/families">Manage families</Link>
            </Button>
          }
        />
      </div>

      <ApiErrorAlert error={error} className="mb-6" />

      <form
        id="skill-form"
        onSubmit={onSubmit}
        className="admin-panel mb-6 space-y-4 rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">
            {editingId ? "Edit catalog skill" : "New catalog skill"}
          </h2>
          {editingId ? (
            <Button
              type="button"
              variant="ghost"
              className="min-h-10"
              onClick={startCreate}
            >
              Cancel edit
            </Button>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="skill-name">Name</Label>
            <Input
              id="skill-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
              className="min-h-11"
              data-testid="catalog-skill-name"
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="skill-number">Number</Label>
            <Input
              id="skill-number"
              value={form.number}
              onChange={(e) =>
                setForm((f) => ({ ...f, number: e.target.value }))
              }
              className="min-h-11"
              data-testid="catalog-skill-number"
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label>Family</Label>
            <Select
              value={form.familyId || undefined}
              onValueChange={(familyId) =>
                setForm((f) => ({ ...f, familyId }))
              }
            >
              <SelectTrigger
                className="min-h-11 w-full"
                data-testid="catalog-skill-family"
              >
                <SelectValue placeholder="Select a family" />
              </SelectTrigger>
              <SelectContent>
                {familyOptions.map((f) => (
                  <SelectItem key={f.familyId} value={f.familyId}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldMessage message={fieldErrors.familyId} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="skill-desc">Description</Label>
            <Textarea
              id="skill-desc"
              value={form.description}
              onChange={(e) =>
                setForm((f) => ({ ...f, description: e.target.value }))
              }
              className="min-h-32"
              maxLength={20000}
              placeholder="Describe this skill area for competitors — shown on the public skill page."
              data-testid="catalog-skill-description"
            />
            <p className="text-xs text-muted-foreground">
              Multi-line text. Appears under “About this skill area” on the
              public site.
            </p>
            <FieldMessage message={fieldErrors.description} />
          </div>
        </div>
        {savedMessage ? (
          <p className="text-sm text-muted-foreground" role="status">
            {savedMessage}
          </p>
        ) : null}
        <Button
          type="submit"
          disabled={pending}
          className="min-h-11"
          data-testid="catalog-skill-save"
        >
          {pending
            ? "Saving…"
            : editingId
              ? "Save changes"
              : "Create skill"}
        </Button>
      </form>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          {skills.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              No catalog skills yet. Create a family first, then add skills.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Skill</TableHead>
                  <TableHead>Family</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((s) => (
                  <TableRow
                    key={s.skillId}
                    data-testid={`catalog-skill-row-${s.skillId}`}
                    className={
                      editingId === s.skillId ? "bg-muted/40" : undefined
                    }
                  >
                    <TableCell className="font-medium">
                      {s.number ? `${s.number} · ` : ""}
                      {s.name}
                    </TableCell>
                    <TableCell>{s.familyName || "—"}</TableCell>
                    <TableCell className="max-w-[14rem]">
                      {s.description?.trim() ? (
                        <span className="line-clamp-2 text-sm text-muted-foreground">
                          {s.description}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground/70">
                          No description
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={s.active ? "default" : "secondary"}>
                        {s.active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => startEdit(s)}
                          data-testid={`catalog-skill-edit-${s.skillId}`}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void toggleActive(s)}
                        >
                          {s.active ? "Deactivate" : "Reactivate"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </PageShell>
  );
}
