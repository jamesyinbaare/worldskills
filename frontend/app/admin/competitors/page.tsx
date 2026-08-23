"use client";

import Link from "next/link";
import { DownloadIcon, MoreHorizontalIcon } from "lucide-react";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import {
  AdminCompetitorItem,
  ApiError,
  exportAdminCompetitorsExcel,
  fetchAdminUploadedConsentForm,
  listAdminCompetitors,
  triggerBrowserDownload,
  verifyConsentForm,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { CompetitorDetailDialog } from "@/components/admin/CompetitorDetailDialog";
import {
  RunCompetitionFilterBar,
  useCompetitionSkillQuery,
} from "@/components/admin/run/useCompetitionSkillQuery";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { cn } from "@/lib/utils";

function displayName(row: AdminCompetitorItem): string {
  const parts = [row.givenNames, row.familyName].filter(Boolean);
  return parts.length ? parts.join(" ") : "—";
}

function consentLabel(row: AdminCompetitorItem): string {
  if (!row.consentFormUploadedAt) return "—";
  return row.consentVerificationStatus || "PENDING";
}

function CompetitorsPageInner() {
  const { filters } = useCompetitionSkillQuery();
  const competitionId = filters.competitionId;

  const [rows, setRows] = useState<AdminCompetitorItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [exportPending, setExportPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectCompetitorId, setRejectCompetitorId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  function openCompetitor(competitorId: string) {
    setSelectedId(competitorId);
  }

  function openReject(competitorId: string) {
    setRejectCompetitorId(competitorId);
    setRejectReason("");
    setRejectOpen(true);
  }

  useEffect(() => {
    if (!competitionId) {
      setRows([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const list = await listAdminCompetitors(competitionId, {
          skillId: filters.skillId || null,
          q: filters.q || null,
        });
        if (!cancelled) setRows(list);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, filters.skillId, filters.q, reloadKey]);

  async function onExportExcel() {
    if (!competitionId) return;
    setExportPending(true);
    setError(null);
    try {
      const { blob, filename } = await exportAdminCompetitorsExcel(competitionId, {
        skillId: filters.skillId || null,
        q: filters.q || null,
      });
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setExportPending(false);
    }
  }

  async function onViewConsent(competitorId: string) {
    setError(null);
    try {
      const { blob } = await fetchAdminUploadedConsentForm(competitorId);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }

  async function onVerify(competitorId: string) {
    setPending(true);
    setError(null);
    setStatusMessage(null);
    try {
      await verifyConsentForm(competitorId, { outcome: "VERIFIED" });
      setStatusMessage("Consent form verified — competitor is now registered.");
      refresh();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPending(false);
    }
  }

  async function onReject(e: FormEvent) {
    e.preventDefault();
    if (!rejectReason.trim()) return;
    setPending(true);
    setError(null);
    setStatusMessage(null);
    try {
      await verifyConsentForm(rejectCompetitorId, {
        outcome: "REJECTED",
        reason: rejectReason.trim(),
      });
      setRejectOpen(false);
      setStatusMessage("Consent form rejected.");
      refresh();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="wide" className="max-w-6xl space-y-5 px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Competitors"
          description="Registered competitors for a competition, filterable by skill area."
          actions={
            competitionId ? (
              <Button
                type="button"
                variant="outline"
                className="min-h-10 gap-1.5"
                disabled={exportPending || loading}
                onClick={() => void onExportExcel()}
              >
                <DownloadIcon className="size-4" aria-hidden />
                {exportPending ? "Downloading…" : "Download Excel"}
              </Button>
            ) : null
          }
        />
      </div>

      <RunCompetitionFilterBar searchPlaceholder="Search name, ref, skill, or school…" />

      {statusMessage ? (
        <Alert>
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}
      <ApiErrorAlert error={error} />

      {!competitionId ? (
        <p className="text-sm text-muted-foreground">
          Select a competition to list registered competitors.
        </p>
      ) : loading ? (
        <Skeleton className="h-48 w-full rounded-2xl" />
      ) : (
        <div className="overflow-hidden rounded-[1.25rem] bg-card shadow-sm ring-1 ring-foreground/5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ref</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Skill</TableHead>
                <TableHead>Institution</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Eligibility</TableHead>
                <TableHead>Consent</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="py-10 text-center text-muted-foreground"
                  >
                    No competitors match these filters.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow
                    key={row.competitorId}
                    role="button"
                    tabIndex={0}
                    aria-label={`View details for ${displayName(row)}`}
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-muted/50",
                      selectedId === row.competitorId && "bg-muted/40",
                    )}
                    onClick={() => openCompetitor(row.competitorId)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openCompetitor(row.competitorId);
                      }
                    }}
                  >
                    <TableCell className="font-mono text-xs">
                      {row.refNo}
                    </TableCell>
                    <TableCell className="font-medium">
                      {displayName(row)}
                    </TableCell>
                    <TableCell>{row.skillName}</TableCell>
                    <TableCell>{row.institutionName || "—"}</TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell>
                      {row.eligibilityStatus ? (
                        <StatusBadge status={row.eligibilityStatus} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      {row.consentFormUploadedAt ? (
                        <StatusBadge status={consentLabel(row)} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 rounded-xl"
                            disabled={pending}
                            aria-label={`Actions for ${row.refNo}`}
                          >
                            <MoreHorizontalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem
                            onClick={() => openCompetitor(row.competitorId)}
                          >
                            View details
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem asChild>
                            <Link
                              href={`/admin/competitions/${competitionId}/competitors/${row.competitorId}/eligibility`}
                            >
                              Eligibility
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link
                              href={`/admin/competitions/${competitionId}/competitors/${row.competitorId}/lifecycle`}
                            >
                              Lifecycle
                            </Link>
                          </DropdownMenuItem>
                          {row.consentFormUploadedAt ? (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => onViewConsent(row.competitorId)}
                              >
                                View consent
                              </DropdownMenuItem>
                              {row.consentVerificationStatus !== "VERIFIED" ? (
                                <DropdownMenuItem
                                  onClick={() => void onVerify(row.competitorId)}
                                >
                                  Verify consent
                                </DropdownMenuItem>
                              ) : null}
                              {row.consentVerificationStatus !== "REJECTED" ? (
                                <DropdownMenuItem
                                  onClick={() => openReject(row.competitorId)}
                                >
                                  Reject consent
                                </DropdownMenuItem>
                              ) : null}
                            </>
                          ) : null}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {competitionId ? (
        <CompetitorDetailDialog
          open={selectedId != null}
          onOpenChange={(open) => {
            if (!open) setSelectedId(null);
          }}
          competitors={rows}
          activeId={selectedId}
          onActiveIdChange={setSelectedId}
          competitionId={competitionId}
          pending={pending}
          onViewConsent={onViewConsent}
          onVerify={(id) => void onVerify(id)}
          onReject={openReject}
        />
      ) : null}

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject consent form</DialogTitle>
            <DialogDescription>
              Provide a reason. The competitor may re-upload a corrected PDF.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onReject} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="rejectReason">Reason</Label>
              <Textarea
                id="rejectReason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                required
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button
                type="submit"
                variant="destructive"
                disabled={pending || !rejectReason.trim()}
              >
                Reject form
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

export default function AdminCompetitorsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <CompetitorsPageInner />
    </Suspense>
  );
}
