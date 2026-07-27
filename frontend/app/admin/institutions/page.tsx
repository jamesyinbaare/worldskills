"use client";

import { ColumnDef, ColumnFiltersState } from "@tanstack/react-table";
import {
  ArrowUpDown,
  DownloadIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
  UploadIcon,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  InstitutionImportResult,
  InstitutionOut,
  RegionOut,
  createInstitution,
  downloadInstitutionsImportTemplate,
  importInstitutions,
  listInstitutions,
  listRegions,
  patchInstitution,
  triggerBrowserDownload,
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
import { DataTable } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

type InstitutionRow = InstitutionOut & { regionName: string };

type SchoolFormState = {
  code: string;
  name: string;
  regionId: string;
};

const EMPTY_FORM: SchoolFormState = { code: "", name: "", regionId: "" };

function SchoolFields({
  idPrefix,
  form,
  onChange,
  fieldErrors,
  regions,
}: {
  idPrefix: string;
  form: SchoolFormState;
  onChange: (next: SchoolFormState) => void;
  fieldErrors: Record<string, string>;
  regions: RegionOut[];
}) {
  return (
    <div className="grid gap-4">
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-code`}>Code</Label>
        <Input
          id={`${idPrefix}-code`}
          value={form.code}
          onChange={(e) => onChange({ ...form, code: e.target.value })}
          required
          className="min-h-10"
          autoComplete="off"
          placeholder="e.g. ACC-001"
        />
        <FieldMessage message={fieldErrors.code} />
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-name`}>Name</Label>
        <Input
          id={`${idPrefix}-name`}
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value })}
          required
          className="min-h-10"
          placeholder="School or training centre name"
        />
        <FieldMessage message={fieldErrors.name} />
      </div>
      <div className="space-y-2">
        <Label>Region</Label>
        <Select
          value={form.regionId || undefined}
          onValueChange={(value) => onChange({ ...form, regionId: value })}
        >
          <SelectTrigger className="min-h-10 w-full">
            <SelectValue placeholder="Select region" />
          </SelectTrigger>
          <SelectContent>
            {regions.map((r) => (
              <SelectItem key={r.regionId} value={r.regionId}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <FieldMessage message={fieldErrors.regionId} />
      </div>
    </div>
  );
}

export default function AdminInstitutionsPage() {
  const [institutions, setInstitutions] = useState<InstitutionOut[]>([]);
  const [regions, setRegions] = useState<RegionOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<SchoolFormState>(EMPTY_FORM);
  const [createPending, setCreatePending] = useState(false);

  const [editing, setEditing] = useState<InstitutionOut | null>(null);
  const [editForm, setEditForm] = useState<SchoolFormState>(EMPTY_FORM);
  const [editPending, setEditPending] = useState(false);

  const [importOpen, setImportOpen] = useState(false);
  const [importPending, setImportPending] = useState(false);
  const [importResult, setImportResult] = useState<InstitutionImportResult | null>(
    null,
  );
  const importInputRef = useRef<HTMLInputElement>(null);

  const [search, setSearch] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const statusFilter =
    (columnFilters.find((f) => f.id === "active")?.value as string | undefined) ??
    "all";
  const regionFilter =
    (columnFilters.find((f) => f.id === "regionName")?.value as
      | string
      | undefined) ?? "all";

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [active, inactive, regionList] = await Promise.all([
        listInstitutions({ active: true }),
        listInstitutions({ active: false }),
        listRegions(),
      ]);
      const byId = new Map<string, InstitutionOut>();
      for (const row of [...active, ...inactive]) {
        byId.set(row.institutionId, row);
      }
      setInstitutions(
        Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name)),
      );
      setRegions(regionList.filter((r) => r.active));
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const regionById = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of regions) map.set(r.regionId, r.name);
    return map;
  }, [regions]);

  const rows: InstitutionRow[] = useMemo(
    () =>
      institutions.map((inst) => ({
        ...inst,
        regionName: inst.regionId
          ? (regionById.get(inst.regionId) ?? inst.regionId)
          : "—",
      })),
    [institutions, regionById],
  );

  function setStatusFilter(value: string) {
    setColumnFilters((prev) => {
      const rest = prev.filter((f) => f.id !== "active");
      if (value === "all") return rest;
      return [...rest, { id: "active", value }];
    });
  }

  function setRegionFilter(value: string) {
    setColumnFilters((prev) => {
      const rest = prev.filter((f) => f.id !== "regionName");
      if (value === "all") return rest;
      return [...rest, { id: "regionName", value }];
    });
  }

  function openCreate() {
    setCreateForm(EMPTY_FORM);
    setFieldErrors({});
    setError(null);
    setCreateOpen(true);
  }

  function openEdit(inst: InstitutionOut) {
    setEditing(inst);
    setEditForm({
      code: inst.code,
      name: inst.name,
      regionId: inst.regionId ?? "",
    });
    setFieldErrors({});
    setError(null);
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreatePending(true);
    setError(null);
    setFieldErrors({});
    try {
      if (!createForm.regionId) {
        setFieldErrors({ regionId: "REQUIRED" });
        setCreatePending(false);
        return;
      }
      await createInstitution({
        code: createForm.code.trim(),
        name: createForm.name.trim(),
        regionId: createForm.regionId,
        active: true,
      });
      setCreateOpen(false);
      setCreateForm(EMPTY_FORM);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setCreatePending(false);
    }
  }

  async function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setEditPending(true);
    setError(null);
    setFieldErrors({});
    try {
      if (!editForm.regionId) {
        setFieldErrors({ regionId: "REQUIRED" });
        setEditPending(false);
        return;
      }
      await patchInstitution(editing.institutionId, {
        code: editForm.code.trim(),
        name: editForm.name.trim(),
        regionId: editForm.regionId,
      });
      setEditing(null);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setEditPending(false);
    }
  }

  async function toggleActive(inst: InstitutionOut) {
    setError(null);
    try {
      await patchInstitution(inst.institutionId, { active: !inst.active });
      await load();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }

  async function onDownloadTemplate() {
    setError(null);
    try {
      const { blob, filename } = await downloadInstitutionsImportTemplate();
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }

  async function onImportFile(file: File | null) {
    if (!file) return;
    setImportPending(true);
    setError(null);
    setImportResult(null);
    try {
      const result = await importInstitutions(file);
      setImportResult(result);
      setImportOpen(false);
      await load();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setImportPending(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  const columns: ColumnDef<InstitutionRow>[] = [
    {
      accessorKey: "code",
      header: ({ column }) => (
        <Button
          type="button"
          variant="ghost"
          className="-ml-3 h-8 px-3 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Code
          <ArrowUpDown className="ml-1.5 size-3.5 opacity-50" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="font-mono text-xs tracking-wide text-muted-foreground">
          {row.original.code}
        </span>
      ),
    },
    {
      accessorKey: "name",
      header: ({ column }) => (
        <Button
          type="button"
          variant="ghost"
          className="-ml-3 h-8 px-3 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          School
          <ArrowUpDown className="ml-1.5 size-3.5 opacity-50" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="font-medium text-foreground">{row.original.name}</span>
      ),
    },
    {
      accessorKey: "regionName",
      header: "Region",
      filterFn: (row, id, value) => {
        if (!value || value === "all") return true;
        return row.getValue(id) === value;
      },
      cell: ({ row }) => (
        <span className="text-muted-foreground">{row.original.regionName}</span>
      ),
    },
    {
      accessorKey: "active",
      header: "Status",
      filterFn: (row, id, value) => {
        if (!value || value === "all") return true;
        const active = row.getValue(id) as boolean;
        return value === "active" ? active : !active;
      },
      cell: ({ row }) =>
        row.original.active ? (
          <Badge variant="secondary" className="font-normal">
            Active
          </Badge>
        ) : (
          <Badge variant="outline" className="font-normal text-muted-foreground">
            Inactive
          </Badge>
        ),
    },
    {
      id: "actions",
      enableSorting: false,
      enableHiding: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const inst = row.original;
        return (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="size-8"
                  aria-label={`Actions for ${inst.name}`}
                >
                  <MoreHorizontalIcon className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem onClick={() => openEdit(inst)}>
                  Edit details
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void toggleActive(inst)}>
                  {inst.active ? "Deactivate" : "Reactivate"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    },
  ];

  const toolbar = (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="relative w-full lg:max-w-md">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search schools…"
          className="min-h-10 rounded-xl pl-9"
          aria-label="Search schools"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger
            className="min-h-10 w-[8.75rem] rounded-xl"
            aria-label="Filter by status"
          >
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
        <Select value={regionFilter} onValueChange={setRegionFilter}>
          <SelectTrigger
            className="min-h-10 w-[11rem] rounded-xl"
            aria-label="Filter by region"
          >
            <SelectValue placeholder="Region" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All regions</SelectItem>
            {regions.map((r) => (
              <SelectItem key={r.regionId} value={r.name}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );

  return (
    <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="mb-6">
        <PageHeader
          className="mb-0"
          title="Institutions"
          description="Schools and training centres used for registration and nominations."
          actions={
            <>
              <Button
                type="button"
                variant="outline"
                className="min-h-10 rounded-xl"
                onClick={() => {
                  setImportResult(null);
                  setImportOpen(true);
                }}
              >
                <UploadIcon className="size-4" />
                Import
              </Button>
              <Button
                type="button"
                className="min-h-10 rounded-xl"
                onClick={openCreate}
              >
                <PlusIcon className="size-4" />
                Add school
              </Button>
            </>
          }
        />
      </div>

      <ApiErrorAlert error={error} className="mb-4" />

      {importResult ? (
        <Alert className="mb-4">
          <AlertTitle className="flex items-center justify-between gap-3">
            <span>Import complete</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-muted-foreground"
              onClick={() => setImportResult(null)}
            >
              Dismiss
            </Button>
          </AlertTitle>
          <AlertDescription>
            <p>
              Created {importResult.created}, updated {importResult.updated}
              {importResult.errors.length > 0
                ? `, ${importResult.errors.length} row error(s)`
                : ""}
              .
            </p>
            {importResult.errors.length > 0 ? (
              <ul className="mt-2 max-h-32 list-disc space-y-1 overflow-y-auto pl-5 text-sm">
                {importResult.errors.map((err, index) => {
                  const detail =
                    err.message ||
                    [err.field, err.reason].filter(Boolean).join(": ") ||
                    "Import error";
                  return (
                    <li key={`${err.row}-${index}`}>
                      Row {err.row}: {detail}
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full max-w-md rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          toolbar={toolbar}
          emptyMessage={
            institutions.length === 0
              ? "No schools yet. Add one or import from Excel."
              : "No schools match your search or filters."
          }
          globalFilter={search}
          onGlobalFilterChange={setSearch}
          columnFilters={columnFilters}
          onColumnFiltersChange={setColumnFilters}
          initialPageSize={10}
          pageSizeOptions={[10, 20, 50]}
        />
      )}

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) {
            setCreateForm(EMPTY_FORM);
            setFieldErrors({});
          }
        }}
      >
        <DialogContent className="sm:max-w-md" showCloseButton>
          <form onSubmit={onCreate} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>Add school</DialogTitle>
              <DialogDescription>
                Codes must be unique. Names may be shared across schools.
              </DialogDescription>
            </DialogHeader>
            <SchoolFields
              idPrefix="create"
              form={createForm}
              onChange={setCreateForm}
              fieldErrors={fieldErrors}
              regions={regions}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateOpen(false)}
                disabled={createPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createPending}>
                {createPending ? "Saving…" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null);
            setFieldErrors({});
          }
        }}
      >
        <DialogContent className="sm:max-w-md" showCloseButton>
          <form onSubmit={onSaveEdit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>Edit school</DialogTitle>
              <DialogDescription>
                Update code, name, or home region.
              </DialogDescription>
            </DialogHeader>
            <SchoolFields
              idPrefix="edit"
              form={editForm}
              onChange={setEditForm}
              fieldErrors={fieldErrors}
              regions={regions}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditing(null)}
                disabled={editPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={editPending}>
                {editPending ? "Saving…" : "Save changes"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-md" showCloseButton>
          <DialogHeader>
            <DialogTitle>Import from Excel</DialogTitle>
            <DialogDescription>
              Download the template, fill school rows, then upload the
              spreadsheet. Rows upsert by school code.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Button
              type="button"
              variant="outline"
              className="min-h-10 justify-start"
              onClick={() => void onDownloadTemplate()}
            >
              <DownloadIcon className="size-4" />
              Download template
            </Button>
            <Button
              type="button"
              className="min-h-10 justify-start"
              disabled={importPending}
              onClick={() => importInputRef.current?.click()}
            >
              <UploadIcon className="size-4" />
              {importPending ? "Importing…" : "Choose Excel file"}
            </Button>
            <input
              ref={importInputRef}
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="sr-only"
              onChange={(e) => {
                void onImportFile(e.target.files?.[0] ?? null);
              }}
            />
          </div>
          <DialogFooter showCloseButton />
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
