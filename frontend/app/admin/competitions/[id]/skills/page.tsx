"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, SkillOut, listSkills } from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/badge";
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

export default function CycleSkillsPage() {
  const params = useParams<{ id: string }>();
  const competitionId = params.id;
  const [skills, setSkills] = useState<SkillOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listSkills(competitionId);
        if (!cancelled) setSkills(list);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  return (
    <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel mb-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Skills"
          description="Associate catalog skills to this competition, then set age rules and pathways."
          backHref={`/admin/competitions/${competitionId}`}
          backLabel="Competition workspace"
          actions={
            <Button className="min-h-11 w-full rounded-2xl sm:w-auto" asChild>
              <Link
                href={`/admin/competitions/${competitionId}/skills/associate`}
              >
                Associate skill
              </Link>
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
          {skills.length === 0 ? (
            <div className="space-y-4 px-5 py-12 text-center sm:px-6">
              <p className="text-sm text-muted-foreground">
                No skills yet. Associate a catalog skill to configure this
                competition.
              </p>
              <Button className="min-h-11 rounded-2xl" asChild>
                <Link
                  href={`/admin/competitions/${competitionId}/skills/associate`}
                >
                  Associate skill
                </Link>
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="px-5 sm:px-6">Skill</TableHead>
                  <TableHead className="hidden md:table-cell">Family</TableHead>
                  <TableHead className="hidden sm:table-cell">Status</TableHead>
                  <TableHead className="pr-5 text-right sm:pr-6">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((s) => {
                  const details = [
                    s.ageRule ? `Max age ${s.ageRule.maxAge}` : null,
                    s.capacity != null ? `Capacity ${s.capacity}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ");

                  return (
                    <TableRow key={s.skillId}>
                      <TableCell className="px-5 sm:px-6">
                        <Link
                          href={`/admin/competitions/${competitionId}/skills/${s.skillId}`}
                          className="font-semibold hover:underline"
                        >
                          {s.name}
                        </Link>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {[s.familyName, details].filter(Boolean).join(" · ") ||
                            "—"}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5 sm:hidden">
                          <Badge
                            variant={s.active ? "secondary" : "outline"}
                            className="font-normal"
                          >
                            {s.active ? "Active" : "Inactive"}
                          </Badge>
                          <Badge
                            variant={s.hasPathway ? "secondary" : "outline"}
                            className="font-normal"
                          >
                            {s.hasPathway ? "Pathway set" : "Pathway missing"}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">
                        {s.familyName || "—"}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <div className="flex flex-wrap gap-1.5">
                          <Badge
                            variant={s.active ? "secondary" : "outline"}
                            className="font-normal"
                          >
                            {s.active ? "Active" : "Inactive"}
                          </Badge>
                          <Badge
                            variant={s.hasPathway ? "secondary" : "outline"}
                            className="font-normal"
                          >
                            {s.hasPathway ? "Pathway set" : "Pathway missing"}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="pr-5 text-right sm:pr-6">
                        <div className="flex flex-wrap items-center justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl"
                            asChild
                          >
                            <Link
                              href={`/admin/competitions/${competitionId}/skills/${s.skillId}`}
                            >
                              Configure
                            </Link>
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl"
                            asChild
                          >
                            <Link
                              href={`/admin/competitions/${competitionId}/skills/${s.skillId}/pathway`}
                            >
                              Pathway
                            </Link>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </PageShell>
  );
}
