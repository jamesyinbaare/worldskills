"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightIcon,
  ClipboardListIcon,
  PlusIcon,
  SparklesIcon,
  UsersRoundIcon,
} from "lucide-react";
import {
  ApiError,
  CompetitionListItem,
  apiFetch,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const CYCLE_STATUSES = [
  {
    key: "DRAFT",
    label: "Draft",
    tone: "bg-slate-100 text-slate-700",
  },
  {
    key: "ACTIVE",
    label: "Active",
    tone: "bg-secondary/15 text-secondary",
  },
  {
    key: "LOCKED",
    label: "Locked",
    tone: "bg-accent/40 text-foreground",
  },
  {
    key: "CLOSED",
    label: "Closed",
    tone: "bg-primary/10 text-primary",
  },
] as const;

function greetingForHour(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function AdminOverviewPage() {
  const { me } = useAuth();
  const [cycles, setCycles] = useState<CompetitionListItem[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const cycleList = await apiFetch<CompetitionListItem[]>("/competitions");
        if (!cancelled) setCycles(cycleList);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const cycleCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of cycles) {
      counts[c.status] = (counts[c.status] ?? 0) + 1;
    }
    return counts;
  }, [cycles]);

  const activeCycles = cycleCounts.ACTIVE ?? 0;

  const highlightedCycles = useMemo(() => {
    const active = cycles.filter((c) => c.status === "ACTIVE");
    const rest = cycles.filter((c) => c.status !== "ACTIVE");
    return [...active, ...rest].slice(0, 6);
  }, [cycles]);

  const firstName = me?.full_name?.split(/\s+/)[0] ?? "there";
  const greeting = greetingForHour(new Date().getHours());

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <section className="admin-panel relative overflow-hidden rounded-[1.75rem] bg-card shadow-[0_12px_40px_-24px_rgba(0,55,100,0.35)] ring-1 ring-foreground/5">
        <div
          className="pointer-events-none absolute inset-0 bg-brand-atmosphere opacity-90"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-brand-blue via-brand-gold to-brand-red"
          aria-hidden
        />
        <div className="relative flex flex-col gap-6 p-6 sm:p-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-3">
            <p className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <SparklesIcon className="size-3.5" />
              Dashboard
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              {greeting}, {firstName}
            </h1>
            <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
              Configure competitions and keep day-of operations moving from one
              calm console.
            </p>
            {!loading && !error ? (
              <p className="text-sm font-medium text-foreground/80">
                {activeCycles} active competition{activeCycles === 1 ? "" : "s"}
                <span className="mx-2 text-border">·</span>
                {cycles.length} total
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button className="min-h-11 rounded-2xl shadow-sm" asChild>
              <Link href="/admin/competitions/new">
                <PlusIcon />
                New cycle
              </Link>
            </Button>
            <Button
              variant="outline"
              className="min-h-11 rounded-2xl border-border/80 bg-card/80 backdrop-blur"
              asChild
            >
              <Link href="/admin/competitors">
                <UsersRoundIcon />
                Competitors
              </Link>
            </Button>
          </div>
        </div>
      </section>

      {loading && (
        <div
          className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
          role="status"
          aria-label="Loading"
        >
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-[1.5rem]" />
          ))}
        </div>
      )}

      <ApiErrorAlert error={error} />

      {!loading && !error && (
        <>
          <section
            aria-labelledby="summary-heading"
            className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
          >
            <h2 id="summary-heading" className="sr-only">
              Summary
            </h2>

            <Link
              href="/admin/competitions"
              className="admin-panel group relative overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 transition-all hover:-translate-y-0.5 hover:shadow-md sm:p-6"
            >
              <span className="absolute -right-6 -top-6 size-24 rounded-full bg-primary/5 transition-transform group-hover:scale-110" />
              <div className="relative flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Total cycles
                  </p>
                  <p className="mt-3 text-4xl font-bold tabular-nums tracking-tight">
                    {cycles.length}
                  </p>
                </div>
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
                  <ClipboardListIcon className="size-5" />
                </span>
              </div>
              <p className="relative mt-5 inline-flex items-center gap-1 text-sm font-semibold text-primary">
                Open competitions
                <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
              </p>
            </Link>

            <Link
              href="/admin/competitions"
              className="admin-panel group relative overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 transition-all hover:-translate-y-0.5 hover:shadow-md sm:p-6"
            >
              <span className="absolute -right-6 -top-6 size-24 rounded-full bg-secondary/10 transition-transform group-hover:scale-110" />
              <div className="relative flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Active now
                  </p>
                  <p className="mt-3 text-4xl font-bold tabular-nums tracking-tight">
                    {activeCycles}
                  </p>
                </div>
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground shadow-sm">
                  <SparklesIcon className="size-5" />
                </span>
              </div>
              <p className="relative mt-5 text-sm text-muted-foreground">
                Live competition windows
              </p>
            </Link>

            <div className="admin-panel rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-6">
              <p className="text-sm font-medium text-muted-foreground">
                Status mix
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {CYCLE_STATUSES.map((status) => (
                  <div
                    key={status.key}
                    className={cn("rounded-2xl px-3 py-2.5", status.tone)}
                  >
                    <p className="text-[0.7rem] font-semibold uppercase tracking-wide opacity-75">
                      {status.label}
                    </p>
                    <p className="mt-0.5 text-xl font-bold tabular-nums">
                      {cycleCounts[status.key] ?? 0}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section
            aria-labelledby="workspace-heading"
            className="admin-panel overflow-hidden rounded-[1.75rem] bg-card shadow-sm ring-1 ring-foreground/5"
          >
            <div className="flex flex-col gap-3 border-b border-border/60 bg-muted/30 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
              <div>
                <h2
                  id="workspace-heading"
                  className="text-lg font-bold tracking-tight"
                >
                  Competitions workspace
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Jump into configuration, nominations, schedule and results.
                </p>
              </div>
              <Button variant="outline" className="min-h-10 rounded-2xl" asChild>
                <Link href="/admin/competitions">View all</Link>
              </Button>
            </div>

            {highlightedCycles.length === 0 ? (
              <div className="flex flex-col items-start gap-4 px-5 py-14 sm:px-7">
                <div className="inline-flex size-14 items-center justify-center rounded-[1.25rem] bg-primary/10 text-primary">
                  <ClipboardListIcon className="size-6" />
                </div>
                <div className="max-w-md space-y-1.5">
                  <p className="text-lg font-semibold text-foreground">
                    Create your first cycle
                  </p>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Competitions isolate competition configuration — skills,
                    pathways, experts and windows all live inside one cycle.
                  </p>
                </div>
                <Button className="min-h-11 rounded-2xl" asChild>
                  <Link href="/admin/competitions/new">
                    <PlusIcon />
                    Create competition
                  </Link>
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-12 px-5 sm:px-7">Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden sm:table-cell">
                      Period
                    </TableHead>
                    <TableHead className="pr-5 text-right sm:pr-7">
                      <span className="sr-only">Open</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {highlightedCycles.map((c) => (
                    <TableRow key={c.competitionId} className="group/row">
                      <TableCell className="px-5 font-semibold sm:px-7">
                        <Link
                          href={`/admin/competitions/${c.competitionId}`}
                          className="text-foreground transition-colors hover:text-primary"
                        >
                          {c.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          status={c.status}
                          className="rounded-full px-2.5"
                        />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground sm:table-cell">
                        {c.period?.start} → {c.period?.end}
                      </TableCell>
                      <TableCell className="pr-5 text-right sm:pr-7">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="min-h-9 rounded-xl opacity-80 group-hover/row:opacity-100"
                          asChild
                        >
                          <Link href={`/admin/competitions/${c.competitionId}`}>
                            Open
                            <ArrowRightIcon />
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
