"use client";

import { ColumnDef } from "@tanstack/react-table";
import {
  ArrowUpDown,
  Download,
  MessageSquareText,
  Route,
  SearchIcon,
  Users,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  AdminCompetitorItem,
  ApiError,
  AssignmentOut,
  SkillOut,
  SkillSmsRecipients,
  SkillSmsSendOut,
  SkillSmsTemplateKey,
  UserOut,
  ZoneOut,
  createAssignment,
  deleteSkillCriteriaDocument,
  downloadSkillCriteriaDocument,
  exportAdminCompetitorsExcel,
  listAdminCompetitors,
  listAssignments,
  listCycleZones,
  listSkills,
  listUsers,
  patchCatalogSkill,
  patchCycleSkill,
  sendSkillSms,
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
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DataTable } from "@/components/ui/data-table";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type CompetitorRow = AdminCompetitorItem & { displayName: string };

const SMS_TEMPLATES: {
  key: SkillSmsTemplateKey;
  label: string;
  description: string;
  body: string;
}[] = [
  {
    key: "exercise_reminder",
    label: "Exercise reminder",
    description: "Point competitors to the portal for exercise details.",
    body: "Reminder for {{competitorName}} — {{skillName}} exercise details are in the competitor portal. {{portalUrl}}",
  },
  {
    key: "schedule_update",
    label: "Schedule update",
    description: "Notify about schedule changes for this skill.",
    body: "Schedule update for {{skillName}}{{zoneLabel}}. Check the portal for details. {{portalUrl}}",
  },
  {
    key: "general_notice",
    label: "General notice",
    description: "Short official notice; add detail in the message field.",
    body: "Notice for {{skillName}} competitors{{zoneLabel}}. {{customNote}} {{portalUrl}}",
  },
  {
    key: "custom",
    label: "Custom message",
    description: "Write your own SMS. Placeholders: {{competitorName}}, {{skillName}}, {{zoneName}}, {{portalUrl}}.",
    body: "",
  },
];

function displayName(row: AdminCompetitorItem): string {
  const name = [row.givenNames, row.familyName].filter(Boolean).join(" ").trim();
  return name || row.refNo || "Competitor";
}

export default function CycleSkillDetailPage() {
  const params = useParams<{ id: string; skillId: string }>();
  const competitionId = params.id;
  const skillId = params.skillId;

  const [skill, setSkill] = useState<SkillOut | null>(null);
  const [assignments, setAssignments] = useState<AssignmentOut[]>([]);
  const [experts, setExperts] = useState<UserOut[]>([]);
  const [competitors, setCompetitors] = useState<AdminCompetitorItem[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("competitors");

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

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [tableSearch, setTableSearch] = useState("");
  const [zoneFilter, setZoneFilter] = useState<string>("all");

  const [smsTemplate, setSmsTemplate] =
    useState<SkillSmsTemplateKey>("exercise_reminder");
  const [smsRecipients, setSmsRecipients] =
    useState<SkillSmsRecipients>("both");
  const [smsMessage, setSmsMessage] = useState(
    SMS_TEMPLATES.find((t) => t.key === "exercise_reminder")?.body ?? "",
  );
  const [smsPending, setSmsPending] = useState(false);
  const [smsError, setSmsError] = useState<ApiError | null>(null);
  const [smsResult, setSmsResult] = useState<SkillSmsSendOut | null>(null);
  const [exportPending, setExportPending] = useState(false);
  const [exportError, setExportError] = useState<ApiError | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [skills, assigns, expertList, cycleZones, skillCompetitors] =
        await Promise.all([
          listSkills(competitionId),
          listAssignments(competitionId, { cycleSkillId: skillId }),
          listUsers({ role: "EXPERT,CHIEF_EXPERT", active: true }),
          listCycleZones(competitionId),
          listAdminCompetitors(competitionId, { skillId }),
        ]);
      const found = skills.find((s) => s.skillId === skillId) ?? null;
      setSkill(found);
      setAssignments(assigns);
      setExperts(expertList);
      setZones(cycleZones.filter((z) => z.active));
      setCompetitors(skillCompetitors);
      setSelectedIds(new Set());
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

  const competitorRows: CompetitorRow[] = useMemo(
    () =>
      competitors.map((c) => ({
        ...c,
        displayName: displayName(c),
      })),
    [competitors],
  );

  const filteredRows = useMemo(() => {
    if (zoneFilter === "all") return competitorRows;
    if (zoneFilter === "none") {
      return competitorRows.filter((r) => !r.zoneId);
    }
    return competitorRows.filter((r) => r.zoneId === zoneFilter);
  }, [competitorRows, zoneFilter]);

  const zoneOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of competitors) {
      if (c.zoneId && c.zoneName) map.set(c.zoneId, c.zoneName);
    }
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [competitors]);

  const allVisibleSelected =
    filteredRows.length > 0 &&
    filteredRows.every((r) => selectedIds.has(r.competitorId));
  const someVisibleSelected =
    filteredRows.some((r) => selectedIds.has(r.competitorId)) &&
    !allVisibleSelected;

  function toggleAllVisible(checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const row of filteredRows) {
        if (checked) next.add(row.competitorId);
        else next.delete(row.competitorId);
      }
      return next;
    });
  }

  function toggleOne(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const columns: ColumnDef<CompetitorRow>[] = useMemo(
    () => [
      {
        id: "select",
        header: () => (
          <Checkbox
            checked={
              allVisibleSelected
                ? true
                : someVisibleSelected
                  ? "indeterminate"
                  : false
            }
            onCheckedChange={(v) => toggleAllVisible(v === true)}
            aria-label="Select all visible competitors"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedIds.has(row.original.competitorId)}
            onCheckedChange={(v) =>
              toggleOne(row.original.competitorId, v === true)
            }
            aria-label={`Select ${row.original.displayName}`}
          />
        ),
        enableSorting: false,
      },
      {
        accessorKey: "displayName",
        header: ({ column }) => (
          <Button
            type="button"
            variant="ghost"
            className="-ml-3 h-8"
            onClick={() =>
              column.toggleSorting(column.getIsSorted() === "asc")
            }
          >
            Competitor
            <ArrowUpDown className="ml-2 size-3.5 opacity-60" />
          </Button>
        ),
        cell: ({ row }) => (
          <div>
            <p className="font-medium text-foreground">
              {row.original.displayName}
            </p>
            <p className="font-mono text-xs text-muted-foreground">
              {row.original.refNo || "—"}
            </p>
          </div>
        ),
      },
      {
        accessorKey: "zoneName",
        header: ({ column }) => (
          <Button
            type="button"
            variant="ghost"
            className="-ml-3 h-8"
            onClick={() =>
              column.toggleSorting(column.getIsSorted() === "asc")
            }
          >
            Zone
            <ArrowUpDown className="ml-2 size-3.5 opacity-60" />
          </Button>
        ),
        cell: ({ row }) =>
          row.original.zoneName ? (
            <span>{row.original.zoneName}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        accessorKey: "institutionName",
        header: "Institution",
        cell: ({ row }) =>
          row.original.institutionName ?? (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        id: "phones",
        header: "SMS contacts",
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1.5">
            <Badge
              variant={row.original.hasMobile ? "secondary" : "outline"}
              className="font-normal"
            >
              Competitor {row.original.hasMobile ? "ready" : "missing"}
            </Badge>
            <Badge
              variant={row.original.hasCoachPhone ? "secondary" : "outline"}
              className="font-normal"
            >
              Coach {row.original.hasCoachPhone ? "ready" : "missing"}
            </Badge>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- selection helpers close over latest filteredRows/selectedIds
    [allVisibleSelected, someVisibleSelected, selectedIds, filteredRows],
  );

  function onTemplateChange(key: SkillSmsTemplateKey) {
    setSmsTemplate(key);
    const preset = SMS_TEMPLATES.find((t) => t.key === key);
    if (key === "general_notice" || key === "custom") {
      setSmsMessage("");
    } else {
      setSmsMessage(preset?.body ?? "");
    }
    setSmsResult(null);
  }

  async function onSendSms() {
    setSmsPending(true);
    setSmsError(null);
    setSmsResult(null);
    try {
      const ids =
        selectedIds.size > 0 ? Array.from(selectedIds) : undefined;
      const out = await sendSkillSms(competitionId, skillId, {
        competitorIds: ids,
        recipients: smsRecipients,
        templateKey: smsTemplate,
        message: smsMessage.trim() || null,
      });
      setSmsResult(out);
    } catch (err) {
      if (err instanceof ApiError) setSmsError(err);
    } finally {
      setSmsPending(false);
    }
  }

  async function onExportCompetitors() {
    setExportPending(true);
    setExportError(null);
    try {
      const { blob, filename } = await exportAdminCompetitorsExcel(
        competitionId,
        { skillId },
      );
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) setExportError(err);
    } finally {
      setExportPending(false);
    }
  }

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
      const assigns = await listAssignments(competitionId, {
        cycleSkillId: skillId,
      });
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

  const zoneNameById = (id: string) =>
    zones.find((z) => z.zoneId === id)?.name ?? id;

  if (loading) {
    return (
      <PageShell width="full" className="space-y-6 px-0 py-0 sm:px-0 sm:py-0">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageShell>
    );
  }

  if (loadError) {
    return (
      <PageShell width="full" className="px-0 py-0 sm:px-0 sm:py-0">
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
      <PageShell width="full" className="px-0 py-0 sm:px-0 sm:py-0">
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

  const selectionLabel =
    selectedIds.size > 0
      ? `${selectedIds.size} selected`
      : `all ${competitors.length} registered`;

  return (
    <PageShell width="full" className="space-y-6 px-0 py-0 sm:px-0 sm:py-0">
      <PageHeader
        title={skill.name}
        description={
          [
            skill.familyName,
            skill.number ? `#${skill.number}` : null,
          ]
            .filter(Boolean)
            .join(" · ") || "Competition skill area"
        }
        backHref={`/admin/competitions/${competitionId}/skills`}
        backLabel="Skills"
        actions={
          <Button variant="outline" className="min-h-11 gap-2" asChild>
            <Link
              href={`/admin/competitions/${competitionId}/skills/${skillId}/pathway`}
            >
              <Route className="size-4" />
              Stage pathway
            </Link>
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="admin-panel rounded-2xl bg-card p-4 shadow-sm ring-1 ring-foreground/5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Competitors
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {competitors.length}
          </p>
          <p className="text-sm text-muted-foreground">Registered for this skill</p>
        </div>
        <div className="admin-panel rounded-2xl bg-card p-4 shadow-sm ring-1 ring-foreground/5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Pathway
          </p>
          <p className="mt-2">
            <Badge variant={skill.hasPathway ? "success" : "secondary"}>
              {skill.hasPathway ? "Configured" : "Not set"}
            </Badge>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Capacity {skill.capacity != null ? skill.capacity : "unlimited"}
          </p>
        </div>
        <div className="admin-panel rounded-2xl bg-card p-4 shadow-sm ring-1 ring-foreground/5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Experts
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {assignments.length}
          </p>
          <p className="text-sm text-muted-foreground">Zone assignments</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="space-y-5">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-muted/50 p-1">
          <TabsTrigger value="competitors" className="gap-1.5 min-h-10">
            <Users className="size-3.5" />
            Competitors & SMS
          </TabsTrigger>
          <TabsTrigger value="settings" className="min-h-10">
            Settings
          </TabsTrigger>
          <TabsTrigger value="experts" className="min-h-10">
            Experts
          </TabsTrigger>
        </TabsList>

        <TabsContent value="competitors" className="space-y-5 outline-none">
          <div className="admin-panel w-full space-y-5 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">
                  Registered competitors
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Select rows to target SMS, or leave empty to message everyone
                  listed for this skill.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="font-normal">
                  {selectionLabel}
                </Badge>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-10 gap-2"
                  disabled={exportPending || competitors.length === 0}
                  onClick={() => void onExportCompetitors()}
                  data-testid="export-competitors-excel"
                >
                  <Download className="size-4" />
                  {exportPending ? "Exporting…" : "Export Excel"}
                </Button>
              </div>
            </div>

            <ApiErrorAlert error={exportError} title="Could not export" />

            <DataTable
              columns={columns}
              data={filteredRows}
              emptyMessage="No competitors registered for this skill yet."
              initialPageSize={10}
              globalFilter={tableSearch}
              onGlobalFilterChange={setTableSearch}
              toolbar={
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="relative min-w-0 flex-1">
                    <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      className="min-h-11 pl-9"
                      placeholder="Search name, ref, institution, zone…"
                      value={tableSearch}
                      onChange={(e) => setTableSearch(e.target.value)}
                    />
                  </div>
                  <Select value={zoneFilter} onValueChange={setZoneFilter}>
                    <SelectTrigger className="min-h-11 w-full sm:w-52">
                      <SelectValue placeholder="All zones" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All zones</SelectItem>
                      <SelectItem value="none">No zone</SelectItem>
                      {zoneOptions.map(([id, name]) => (
                        <SelectItem key={id} value={id}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              }
            />
          </div>

          <div className="admin-panel w-full space-y-5 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-lg bg-muted p-2">
                <MessageSquareText className="size-5 text-foreground" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">
                  Send SMS
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose a template, who receives it, then send to{" "}
                  <span className="font-medium text-foreground">
                    {selectionLabel}
                  </span>
                  .
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {SMS_TEMPLATES.map((t) => {
                const active = smsTemplate === t.key;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => onTemplateChange(t.key)}
                    className={
                      active
                        ? "rounded-xl border border-foreground/20 bg-muted/60 p-3 text-left ring-2 ring-foreground/15"
                        : "rounded-xl border border-border bg-background p-3 text-left transition hover:border-foreground/20 hover:bg-muted/30"
                    }
                    data-testid={`sms-template-${t.key}`}
                  >
                    <p className="text-sm font-medium">{t.label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t.description}
                    </p>
                  </button>
                );
              })}
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,14rem)_minmax(0,14rem)_minmax(0,1fr)] lg:items-start">
              <div className="space-y-2">
                <Label>Send to</Label>
                <Select
                  value={smsRecipients}
                  onValueChange={(v) =>
                    setSmsRecipients(v as SkillSmsRecipients)
                  }
                >
                  <SelectTrigger
                    className="min-h-11 w-full"
                    data-testid="sms-recipients"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="competitors">
                      Competitors only
                    </SelectItem>
                    <SelectItem value="coaches">Coaches only</SelectItem>
                    <SelectItem value="both">
                      Competitors and coaches
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Audience</Label>
                <div className="flex min-h-11 items-center rounded-lg border border-border px-3 text-sm text-muted-foreground">
                  {selectedIds.size > 0
                    ? `${selectedIds.size} selected competitor(s)`
                    : "Everyone registered for this skill"}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sms-body">
                  {smsTemplate === "general_notice"
                    ? "Notice detail"
                    : "Message"}
                </Label>
                {smsTemplate === "general_notice" ? (
                  <p className="rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground">
                    {
                      SMS_TEMPLATES.find((t) => t.key === "general_notice")
                        ?.body
                    }
                  </p>
                ) : null}
                <Textarea
                  id="sms-body"
                  className="min-h-28 font-mono text-sm"
                  value={smsMessage}
                  onChange={(e) => setSmsMessage(e.target.value)}
                  placeholder={
                    smsTemplate === "custom"
                      ? "Type the SMS body…"
                      : smsTemplate === "general_notice"
                        ? "Short detail inserted as {{customNote}}…"
                        : "Edit the template body if needed…"
                  }
                  data-testid="sms-message"
                />
                <p className="text-xs text-muted-foreground">
                  Placeholders:{" "}
                  <code className="rounded bg-muted px-1">
                    {"{{competitorName}}"}
                  </code>
                  ,{" "}
                  <code className="rounded bg-muted px-1">
                    {"{{skillName}}"}
                  </code>
                  ,{" "}
                  <code className="rounded bg-muted px-1">
                    {"{{zoneName}}"}
                  </code>
                  ,{" "}
                  <code className="rounded bg-muted px-1">
                    {"{{portalUrl}}"}
                  </code>
                  {smsTemplate === "general_notice" ? (
                    <>
                      ,{" "}
                      <code className="rounded bg-muted px-1">
                        {"{{customNote}}"}
                      </code>
                    </>
                  ) : null}
                </p>
              </div>
            </div>

            <ApiErrorAlert error={smsError} title="Could not send SMS" />
            {smsResult ? (
              <Alert data-testid="sms-send-result">
                <AlertTitle>SMS queued</AlertTitle>
                <AlertDescription>
                  Considered {smsResult.competitorsConsidered} competitor(s) ·
                  sent to {smsResult.competitorSent} competitor(s) and{" "}
                  {smsResult.coachSent} coach(es)
                  {smsResult.failed
                    ? ` · ${smsResult.failed} failed`
                    : ""}
                  {smsResult.skippedNoPhone
                    ? ` · ${smsResult.skippedNoPhone} missing phone`
                    : ""}
                  .
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                className="min-h-11"
                disabled={smsPending || competitors.length === 0}
                onClick={() => void onSendSms()}
                data-testid="sms-send"
              >
                {smsPending ? "Sending…" : "Send SMS"}
              </Button>
              {selectedIds.size > 0 ? (
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Clear selection
                </Button>
              ) : null}
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="settings"
          className="grid gap-5 outline-none xl:grid-cols-2 xl:items-start"
        >
          <div className="admin-panel space-y-5 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Public description
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Shown on the public skill area page. Shared across competitions
                that use this catalog skill.
              </p>
            </div>
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
                <ApiErrorAlert
                  error={descError}
                  title="Could not save description"
                />
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
                This skill is not linked to the catalog. Associate a catalog
                skill or edit under{" "}
                <Link href="/admin/skills" className="font-medium underline">
                  Skills catalog
                </Link>
                .
              </p>
            )}
          </div>

          <div className="admin-panel space-y-5 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Age rule and capacity
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                One age rule per skill for this competition. Capacity limits
                registrations when set.
              </p>
            </div>
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
          </div>

          <div className="admin-panel space-y-5 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Skill-area criteria
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Upload the criteria document. Competitors and institutions can
                download it.
              </p>
            </div>
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
          </div>
        </TabsContent>

        <TabsContent value="experts" className="outline-none">
          <div className="admin-panel space-y-6 overflow-hidden rounded-3xl bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Expert assignments
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Assign experts to this skill and zone. Conflict-of-interest
                flags are returned when detected.
              </p>
            </div>

            {assignments.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No experts assigned yet.
              </p>
            ) : (
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
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
                        <TableCell>{zoneNameById(a.zoneId)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            <Separator />

            <form onSubmit={onAssignExpert} className="space-y-4" noValidate>
              <div className="grid gap-4 sm:grid-cols-2">
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
          </div>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
