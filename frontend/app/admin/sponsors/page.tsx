"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  CatalogSkillOut,
  SponsorOut,
  createSponsor,
  deleteSponsorLogo,
  fetchSponsorLogo,
  listCatalogSkills,
  listSponsors,
  patchSponsor,
  uploadSponsorLogo,
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Textarea } from "@/components/ui/textarea";

function skillLabel(skill: { name: string; number?: string | null }) {
  return skill.number ? `${skill.name} (${skill.number})` : skill.name;
}

function formatSkillAreas(sponsor: SponsorOut): string {
  const areas = sponsor.skillAreas ?? [];
  if (areas.length === 0) return "General";
  const names = areas.map((a) => a.name);
  if (names.length <= 2) return names.join(", ");
  return `${names.slice(0, 2).join(", ")} +${names.length - 2}`;
}

function SkillAreaChecklist({
  skills,
  selectedIds,
  onToggle,
  idPrefix,
}: {
  skills: CatalogSkillOut[];
  selectedIds: string[];
  onToggle: (skillId: string, checked: boolean) => void;
  idPrefix: string;
}) {
  if (skills.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No active catalog skill areas yet.
      </p>
    );
  }

  return (
    <div className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-border p-3">
      {skills.map((skill) => {
        const checked = selectedIds.includes(skill.skillId);
        const inputId = `${idPrefix}-${skill.skillId}`;
        return (
          <label
            key={skill.skillId}
            htmlFor={inputId}
            className="flex cursor-pointer items-start gap-2.5 text-sm"
          >
            <Checkbox
              id={inputId}
              checked={checked}
              onCheckedChange={(value) =>
                onToggle(skill.skillId, value === true)
              }
              className="mt-0.5"
            />
            <span>{skillLabel(skill)}</span>
          </label>
        );
      })}
    </div>
  );
}

function SponsorLogoThumb({
  sponsorId,
  hasLogo,
  name,
}: {
  sponsorId: string;
  hasLogo: boolean;
  name: string;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!hasLogo) {
      setSrc(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const { blob } = await fetchSponsorLogo(sponsorId);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setSrc(null);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sponsorId, hasLogo]);

  if (!hasLogo || !src) {
    return (
      <div
        className="flex size-10 items-center justify-center rounded-lg bg-muted text-xs font-semibold text-muted-foreground"
        aria-hidden
      >
        {name.slice(0, 1).toUpperCase()}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- blob: from API
    <img
      src={src}
      alt=""
      className="size-10 rounded-lg object-contain bg-white ring-1 ring-border"
    />
  );
}

export default function AdminSponsorsPage() {
  const [sponsors, setSponsors] = useState<SponsorOut[]>([]);
  const [catalogSkills, setCatalogSkills] = useState<CatalogSkillOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [description, setDescription] = useState("");
  const [createLogo, setCreateLogo] = useState<File | null>(null);
  const [createSkillIds, setCreateSkillIds] = useState<string[]>([]);

  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<SponsorOut | null>(null);
  const [editName, setEditName] = useState("");
  const [editWebsite, setEditWebsite] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editLogo, setEditLogo] = useState<File | null>(null);
  const [editSkillIds, setEditSkillIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sponsorList, skills] = await Promise.all([
        listSponsors(),
        listCatalogSkills({ active: true }),
      ]);
      setSponsors(sponsorList);
      setCatalogSkills(skills);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleCreateSkill(skillId: string, checked: boolean) {
    setCreateSkillIds((prev) =>
      checked ? [...prev, skillId] : prev.filter((id) => id !== skillId),
    );
  }

  function toggleEditSkill(skillId: string, checked: boolean) {
    setEditSkillIds((prev) =>
      checked ? [...prev, skillId] : prev.filter((id) => id !== skillId),
    );
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const created = await createSponsor({
        name: name.trim(),
        website: website.trim() || null,
        description: description.trim() || null,
        catalogSkillIds: createSkillIds,
      });
      if (createLogo) {
        await uploadSponsorLogo(created.sponsorId, createLogo);
      }
      setName("");
      setWebsite("");
      setDescription("");
      setCreateLogo(null);
      setCreateSkillIds([]);
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

  function openEdit(sponsor: SponsorOut) {
    setEditing(sponsor);
    setEditName(sponsor.name);
    setEditWebsite(sponsor.website || "");
    setEditDescription(sponsor.description || "");
    setEditLogo(null);
    const activeIds = new Set(catalogSkills.map((s) => s.skillId));
    setEditSkillIds(
      (sponsor.skillAreas ?? [])
        .map((a) => a.catalogSkillId)
        .filter((id) => activeIds.has(id)),
    );
    setFieldErrors({});
    setEditOpen(true);
  }

  async function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      await patchSponsor(editing.sponsorId, {
        name: editName.trim(),
        website: editWebsite.trim() || null,
        description: editDescription.trim() || null,
        catalogSkillIds: editSkillIds,
      });
      if (editLogo) {
        await uploadSponsorLogo(editing.sponsorId, editLogo);
      }
      setEditOpen(false);
      setEditing(null);
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

  async function toggleActive(sponsor: SponsorOut) {
    setError(null);
    try {
      await patchSponsor(sponsor.sponsorId, { active: !sponsor.active });
      await load();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }

  async function onRemoveLogo(sponsor: SponsorOut) {
    setError(null);
    try {
      await deleteSponsorLogo(sponsor.sponsorId);
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
          title="Sponsors"
          description="Manage sponsorship partners — name required; logo, website, description, and skill areas optional."
        />
      </div>

      <ApiErrorAlert error={error} className="mb-6" />

      <form
        onSubmit={onCreate}
        className="admin-panel mb-6 space-y-4 rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6"
      >
        <h2 className="text-sm font-semibold">New sponsor</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="sponsor-name">Name</Label>
            <Input
              id="sponsor-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="min-h-11"
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sponsor-website">Website (optional)</Label>
            <Input
              id="sponsor-website"
              type="url"
              placeholder="https://"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              className="min-h-11"
            />
            <FieldMessage message={fieldErrors.website} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="sponsor-desc">Description (optional)</Label>
            <Textarea
              id="sponsor-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label>Skill areas (optional)</Label>
            <p className="text-xs text-muted-foreground">
              Leave empty if this partner is not skill-specific.
            </p>
            <SkillAreaChecklist
              skills={catalogSkills}
              selectedIds={createSkillIds}
              onToggle={toggleCreateSkill}
              idPrefix="create-skill"
            />
            <FieldMessage message={fieldErrors.catalogSkillIds} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="sponsor-logo">Logo (optional)</Label>
            <Input
              id="sponsor-logo"
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              className="min-h-11"
              onChange={(e) => setCreateLogo(e.target.files?.[0] ?? null)}
            />
            <FieldMessage message={fieldErrors.file} />
          </div>
        </div>
        <Button type="submit" disabled={pending} className="min-h-11">
          {pending ? "Saving…" : "Create sponsor"}
        </Button>
      </form>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          {sponsors.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              No sponsors yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-14">Logo</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead className="hidden md:table-cell">
                    Skill areas
                  </TableHead>
                  <TableHead className="hidden lg:table-cell">Website</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sponsors.map((s) => (
                  <TableRow key={s.sponsorId}>
                    <TableCell>
                      <SponsorLogoThumb
                        sponsorId={s.sponsorId}
                        hasLogo={s.hasLogo}
                        name={s.name}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{s.name}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="text-sm text-muted-foreground">
                        {formatSkillAreas(s)}
                      </span>
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {s.website ? (
                        <a
                          href={s.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-brand-blue underline-offset-4 hover:underline"
                        >
                          {s.website.replace(/^https?:\/\//, "")}
                        </a>
                      ) : (
                        <span className="text-muted-foreground">—</span>
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
                          onClick={() => openEdit(s)}
                        >
                          Edit
                        </Button>
                        {s.hasLogo ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void onRemoveLogo(s)}
                          >
                            Remove logo
                          </Button>
                        ) : null}
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

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit sponsor</DialogTitle>
          </DialogHeader>
          <form onSubmit={onSaveEdit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-sponsor-name">Name</Label>
              <Input
                id="edit-sponsor-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
                className="min-h-11"
              />
              <FieldMessage message={fieldErrors.name} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-sponsor-website">Website</Label>
              <Input
                id="edit-sponsor-website"
                type="url"
                value={editWebsite}
                onChange={(e) => setEditWebsite(e.target.value)}
                className="min-h-11"
              />
              <FieldMessage message={fieldErrors.website} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-sponsor-desc">Description</Label>
              <Textarea
                id="edit-sponsor-desc"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label>Skill areas (optional)</Label>
              <p className="text-xs text-muted-foreground">
                Leave empty if this partner is not skill-specific.
              </p>
              <SkillAreaChecklist
                skills={catalogSkills}
                selectedIds={editSkillIds}
                onToggle={toggleEditSkill}
                idPrefix="edit-skill"
              />
              <FieldMessage message={fieldErrors.catalogSkillIds} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-sponsor-logo">
                {editing?.hasLogo ? "Replace logo" : "Add logo"}
              </Label>
              <Input
                id="edit-sponsor-logo"
                type="file"
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                className="min-h-11"
                onChange={(e) => setEditLogo(e.target.files?.[0] ?? null)}
              />
              <FieldMessage message={fieldErrors.file} />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending} className="min-h-11">
                {pending ? "Saving…" : "Save changes"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
