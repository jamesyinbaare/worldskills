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

export default function AdminSkillsCatalogPage() {
  const [skills, setSkills] = useState<CatalogSkillOut[]>([]);
  const [families, setFamilies] = useState<FamilyOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [number, setNumber] = useState("");
  const [description, setDescription] = useState("");
  const [familyId, setFamilyId] = useState("");
  const [pending, setPending] = useState(false);
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

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      if (!familyId) {
        setFieldErrors({ familyId: "REQUIRED" });
        setPending(false);
        return;
      }
      await createCatalogSkill({
        name: name.trim(),
        number: number.trim() || null,
        familyId,
        description: description.trim() || null,
      });
      setName("");
      setNumber("");
      setDescription("");
      setFamilyId("");
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

  return (
    <PageShell width="wide" className="max-w-5xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel mb-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Skills catalog"
          description="Global skills reused across cycles. Associate a skill to a competition from the competition workspace."
          actions={
            <Button variant="outline" className="min-h-11" asChild>
              <Link href="/admin/families">Manage families</Link>
            </Button>
          }
        />
      </div>

      <ApiErrorAlert error={error} className="mb-6" />

      <form
        onSubmit={onCreate}
        className="admin-panel mb-6 space-y-4 rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6"
      >
        <h2 className="text-sm font-semibold">New catalog skill</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="skill-name">Name</Label>
            <Input
              id="skill-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="min-h-11"
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="skill-number">Number</Label>
            <Input
              id="skill-number"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              className="min-h-11"
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label>Family</Label>
            <Select value={familyId || undefined} onValueChange={setFamilyId}>
              <SelectTrigger className="min-h-11 w-full">
                <SelectValue placeholder="Select a family" />
              </SelectTrigger>
              <SelectContent>
                {families.map((f) => (
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
            <Input
              id="skill-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-11"
            />
          </div>
        </div>
        <Button type="submit" disabled={pending} className="min-h-11">
          {pending ? "Saving…" : "Create skill"}
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
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((s) => (
                  <TableRow key={s.skillId}>
                    <TableCell className="font-medium">
                      {s.number ? `${s.number} · ` : ""}
                      {s.name}
                    </TableCell>
                    <TableCell>{s.familyName || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={s.active ? "default" : "secondary"}>
                        {s.active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void toggleActive(s)}
                      >
                        {s.active ? "Deactivate" : "Reactivate"}
                      </Button>
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
