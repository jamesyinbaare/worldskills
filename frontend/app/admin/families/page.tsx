"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  FamilyOut,
  createFamily,
  listFamilies,
  patchFamily,
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AdminFamiliesPage() {
  const [families, setFamilies] = useState<FamilyOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setFamilies(await listFamilies());
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
      await createFamily({
        name: name.trim(),
        description: description.trim() || null,
      });
      setName("");
      setDescription("");
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

  async function toggleActive(family: FamilyOut) {
    setError(null);
    try {
      await patchFamily(family.familyId, { active: !family.active });
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
          title="Skill families"
          description="Global catalog of skill families. Assign a family when creating catalog skills."
        />
      </div>

      <ApiErrorAlert error={error} className="mb-6" />

      <form
        onSubmit={onCreate}
        className="admin-panel mb-6 space-y-4 rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6"
      >
        <h2 className="text-sm font-semibold">New family</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="family-name">Name</Label>
            <Input
              id="family-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="min-h-11"
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="family-desc">Description</Label>
            <Input
              id="family-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-11"
            />
          </div>
        </div>
        <Button type="submit" disabled={pending} className="min-h-11">
          {pending ? "Saving…" : "Create family"}
        </Button>
      </form>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          {families.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              No families yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Name</TableHead>
                  <TableHead className="hidden sm:table-cell">Description</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {families.map((f) => (
                  <TableRow key={f.familyId}>
                    <TableCell className="font-medium">{f.name}</TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">
                      {f.description || "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={f.active ? "default" : "secondary"}>
                        {f.active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void toggleActive(f)}
                      >
                        {f.active ? "Deactivate" : "Reactivate"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      <p className="mt-4 text-sm text-muted-foreground">
        Next:{" "}
        <Link href="/admin/skills" className="underline underline-offset-2">
          manage catalog skills
        </Link>
      </p>
    </PageShell>
  );
}
