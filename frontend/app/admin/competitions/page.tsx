"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, CompetitionListItem, apiFetch } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
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

export default function AdminCyclesPage() {
  const [cycles, setCycles] = useState<CompetitionListItem[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await apiFetch<CompetitionListItem[]>("/competitions");
        if (!cancelled) setCycles(list);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel mb-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Competitions"
          description="Create, validate and activate isolated competitions."
          actions={
            <Button className="min-h-11 rounded-2xl" asChild>
              <Link href="/admin/competitions/new">New cycle</Link>
            </Button>
          }
        />
      </div>

      {loading && (
        <div className="space-y-3" role="status" aria-label="Loading">
          <Skeleton className="h-28 rounded-[1.5rem]" />
          <Skeleton className="h-28 rounded-[1.5rem]" />
        </div>
      )}

      <ApiErrorAlert error={error} className="mb-6" />

      {!loading && !error && (
        <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card shadow-sm ring-1 ring-foreground/5">
          {cycles.length === 0 ? (
            <p className="px-5 py-12 text-sm text-muted-foreground sm:px-6">
              No cycles yet. Create the first draft to begin configuration.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="px-5 sm:px-6">Competition</TableHead>
                  <TableHead className="hidden sm:table-cell">Period</TableHead>
                  <TableHead className="pr-5 sm:pr-6">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cycles.map((c) => (
                  <TableRow key={c.competitionId}>
                    <TableCell className="px-5 sm:px-6">
                      <Button
                        variant="link"
                        className="h-auto min-h-11 justify-start px-0 text-base font-semibold"
                        asChild
                      >
                        <Link href={`/admin/competitions/${c.competitionId}`}>{c.name}</Link>
                      </Button>
                      <p className="text-xs text-muted-foreground sm:hidden">
                        {c.period.start} → {c.period.end}
                      </p>
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">
                      {c.period.start} → {c.period.end} · {c.timeZone}
                    </TableCell>
                    <TableCell className="pr-5 sm:pr-6">
                      <StatusBadge
                        status={c.status}
                        className="rounded-full px-2.5"
                      />
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
