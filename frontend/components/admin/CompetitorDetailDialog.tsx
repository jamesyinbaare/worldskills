"use client";

import Link from "next/link";
import { useCallback, useEffect, type ReactNode } from "react";
import {
  Building2Icon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FileTextIcon,
  MapPinIcon,
  RouteIcon,
  ShieldCheckIcon,
  WrenchIcon,
} from "lucide-react";
import type { AdminCompetitorItem } from "@/lib/api";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

function displayName(row: AdminCompetitorItem): string {
  const parts = [row.givenNames, row.familyName].filter(Boolean);
  return parts.length ? parts.join(" ") : "—";
}

function initials(row: AdminCompetitorItem): string {
  const given = row.givenNames?.trim()?.[0];
  const family = row.familyName?.trim()?.[0];
  if (given && family) return `${given}${family}`.toUpperCase();
  if (given) return given.toUpperCase();
  if (family) return family.toUpperCase();
  return "?";
}

function consentLabel(row: AdminCompetitorItem): string {
  if (!row.consentFormUploadedAt) return "—";
  return row.consentVerificationStatus || "PENDING";
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-[0.7rem] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

function InfoTile({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-muted/45 p-4 ring-1 ring-foreground/5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 space-y-1">
          <p className="text-[0.65rem] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
            {label}
          </p>
          <div className="text-sm leading-snug font-medium text-foreground">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusPanel({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex min-h-22 flex-col justify-between gap-3 rounded-2xl bg-card p-4 ring-1 ring-foreground/8">
      <p className="text-[0.65rem] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
        {label}
      </p>
      <div className="space-y-1">
        <div>{children}</div>
        {hint ? (
          <p className="text-xs text-muted-foreground">{hint}</p>
        ) : null}
      </div>
    </div>
  );
}

export type CompetitorDetailDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  competitors: AdminCompetitorItem[];
  activeId: string | null;
  onActiveIdChange: (id: string) => void;
  competitionId: string;
  pending?: boolean;
  onViewConsent?: (competitorId: string) => void;
  onVerify?: (competitorId: string) => void;
  onReject?: (competitorId: string) => void;
};

export function CompetitorDetailDialog({
  open,
  onOpenChange,
  competitors,
  activeId,
  onActiveIdChange,
  competitionId,
  pending = false,
  onViewConsent,
  onVerify,
  onReject,
}: CompetitorDetailDialogProps) {
  const index = activeId
    ? competitors.findIndex((c) => c.competitorId === activeId)
    : -1;
  const current = index >= 0 ? competitors[index] : null;
  const total = competitors.length;
  const canPrev = index > 0;
  const canNext = index >= 0 && index < total - 1;

  const goPrev = useCallback(() => {
    if (!canPrev) return;
    onActiveIdChange(competitors[index - 1]!.competitorId);
  }, [canPrev, competitors, index, onActiveIdChange]);

  const goNext = useCallback(() => {
    if (!canNext) return;
    onActiveIdChange(competitors[index + 1]!.competitorId);
  }, [canNext, competitors, index, onActiveIdChange]);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable
      ) {
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        goNext();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, goPrev, goNext]);

  useEffect(() => {
    if (!open || !activeId) return;
    if (competitors.some((c) => c.competitorId === activeId)) return;
    onOpenChange(false);
  }, [open, activeId, competitors, onOpenChange]);

  const name = current ? displayName(current) : "Competitor";
  const consentUploaded = Boolean(current?.consentFormUploadedAt);
  const consentHint = !current
    ? undefined
    : !consentUploaded
      ? "No form uploaded yet"
      : current.consentVerificationStatus === "VERIFIED"
        ? "Form verified"
        : current.consentVerificationStatus === "REJECTED"
          ? "Form rejected — awaiting re-upload"
          : "Awaiting verification";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "flex h-[min(92vh,56rem)] w-full max-w-[calc(100%-1.25rem)] flex-col gap-0 overflow-hidden p-0",
          "rounded-2xl sm:max-w-4xl sm:rounded-3xl",
        )}
        data-testid="competitor-detail-dialog"
      >
        {current ? (
          <>
            {/* Sticky top nav */}
            <div className="relative z-20 flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-brand-blue px-4 py-2.5 pr-12 text-white sm:px-5">
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-9 rounded-xl text-white hover:bg-white/12 hover:text-white disabled:opacity-35"
                  disabled={!canPrev}
                  onClick={goPrev}
                  aria-label="Previous competitor"
                >
                  <ChevronLeftIcon className="size-5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-9 rounded-xl text-white hover:bg-white/12 hover:text-white disabled:opacity-35"
                  disabled={!canNext}
                  onClick={goNext}
                  aria-label="Next competitor"
                >
                  <ChevronRightIcon className="size-5" />
                </Button>
              </div>
              <p
                className="text-xs font-medium tracking-wide text-white/75 tabular-nums"
                aria-live="polite"
              >
                {index + 1}
                <span className="text-white/45"> / </span>
                {total}
              </p>
              <p className="hidden text-[0.7rem] tracking-wide text-white/50 sm:block">
                ← → to browse
              </p>
            </div>

            <div
              key={current.competitorId}
              className="flex min-h-0 flex-1 flex-col animate-in fade-in-0 duration-200"
            >
              {/* Hero identity */}
              <DialogHeader className="relative shrink-0 space-y-0 overflow-hidden bg-brand-blue px-5 pt-6 pb-8 text-white sm:px-8 sm:pt-8 sm:pb-10">
                <div
                  className="pointer-events-none absolute inset-0"
                  aria-hidden
                >
                  <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_15%_0%,rgba(255,204,0,0.22),transparent_55%)]" />
                  <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_45%_at_100%_80%,rgba(0,133,63,0.28),transparent_50%)]" />
                  <div className="absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-transparent via-brand-gold/50 to-transparent" />
                </div>

                <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
                  <div className="flex min-w-0 items-start gap-4 sm:gap-5">
                    <div
                      className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-white/12 text-xl font-bold tracking-tight text-white ring-1 ring-white/25 shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] sm:size-20 sm:text-2xl"
                      aria-hidden
                    >
                      {initials(current)}
                    </div>
                    <div className="min-w-0 space-y-2 pt-0.5">
                      <p className="text-[0.65rem] font-semibold tracking-[0.2em] text-brand-gold uppercase">
                        Competitor
                      </p>
                      <DialogTitle className="truncate text-2xl font-bold tracking-tight text-white sm:text-3xl">
                        {name}
                      </DialogTitle>
                      <DialogDescription className="font-mono text-sm text-white/65">
                        {current.refNo || current.competitorId}
                      </DialogDescription>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge status={current.status} />
                    {current.eligibilityStatus ? (
                      <StatusBadge status={current.eligibilityStatus} />
                    ) : null}
                  </div>
                </div>
              </DialogHeader>

              {/* Scrollable body */}
              <div className="min-h-0 flex-1 overflow-y-auto bg-(--admin-canvas) px-5 py-6 sm:px-8 sm:py-7">
                <div className="mx-auto flex max-w-3xl flex-col gap-7">
                  <section className="space-y-3">
                    <SectionHeading>At a glance</SectionHeading>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <StatusPanel label="Registration">
                        <StatusBadge status={current.status} />
                      </StatusPanel>
                      <StatusPanel
                        label="Eligibility"
                        hint={
                          current.eligibilityStatus
                            ? undefined
                            : "Not screened yet"
                        }
                      >
                        {current.eligibilityStatus ? (
                          <StatusBadge status={current.eligibilityStatus} />
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            —
                          </span>
                        )}
                      </StatusPanel>
                      <StatusPanel label="Consent" hint={consentHint}>
                        {consentUploaded ? (
                          <StatusBadge status={consentLabel(current)} />
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            —
                          </span>
                        )}
                      </StatusPanel>
                    </div>
                  </section>

                  <section className="space-y-3">
                    <SectionHeading>Placement</SectionHeading>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <InfoTile icon={WrenchIcon} label="Skill area">
                        {current.skillName}
                      </InfoTile>
                      <InfoTile icon={Building2Icon} label="Institution">
                        {current.institutionName || "—"}
                      </InfoTile>
                      <InfoTile icon={MapPinIcon} label="Zone">
                        {current.zoneName || "—"}
                      </InfoTile>
                      <InfoTile icon={FileTextIcon} label="Reference">
                        <span className="font-mono text-xs sm:text-sm">
                          {current.refNo || current.competitorId}
                        </span>
                      </InfoTile>
                    </div>
                  </section>

                  {consentUploaded ? (
                    <section className="space-y-3">
                      <SectionHeading>Consent form</SectionHeading>
                      <div className="flex flex-col gap-3 rounded-2xl bg-card p-4 ring-1 ring-foreground/8 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:p-5">
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-foreground">
                            Guardian consent PDF on file
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {consentHint}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {onViewConsent ? (
                            <Button
                              type="button"
                              variant="outline"
                              className="min-h-10 gap-1.5"
                              disabled={pending}
                              onClick={() =>
                                onViewConsent(current.competitorId)
                              }
                            >
                              <FileTextIcon className="size-4" aria-hidden />
                              View PDF
                            </Button>
                          ) : null}
                          {onVerify &&
                          current.consentVerificationStatus !== "VERIFIED" ? (
                            <Button
                              type="button"
                              variant="default"
                              className="min-h-10"
                              disabled={pending}
                              onClick={() => onVerify(current.competitorId)}
                            >
                              Verify
                            </Button>
                          ) : null}
                          {onReject &&
                          current.consentVerificationStatus !== "REJECTED" ? (
                            <Button
                              type="button"
                              variant="destructive"
                              className="min-h-10"
                              disabled={pending}
                              onClick={() => onReject(current.competitorId)}
                            >
                              Reject
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </section>
                  ) : null}
                </div>
              </div>
            </div>

            {/* Sticky footer actions */}
            <div className="shrink-0 border-t border-border bg-card px-5 py-4 sm:px-8">
              <div className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-muted-foreground">
                  Open full screens for eligibility screening or lifecycle
                  changes.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline" className="min-h-10 gap-1.5">
                    <Link
                      href={`/admin/competitions/${competitionId}/competitors/${current.competitorId}/eligibility`}
                    >
                      <ShieldCheckIcon className="size-4" aria-hidden />
                      Eligibility
                    </Link>
                  </Button>
                  <Button asChild variant="accent" className="min-h-10 gap-1.5">
                    <Link
                      href={`/admin/competitions/${competitionId}/competitors/${current.competitorId}/lifecycle`}
                    >
                      <RouteIcon className="size-4" aria-hidden />
                      Lifecycle
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
