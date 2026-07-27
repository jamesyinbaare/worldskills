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
    <PageShell>
      <PageHeader
        title="Skills"
        description="Associate catalog skills to this competition, then set age rules and pathways."
        backHref={`/admin/competitions/${competitionId}`}
        backLabel="Competition workspace"
        actions={
          <Button className="min-h-11 w-full sm:w-auto" asChild>
            <Link href={`/admin/competitions/${competitionId}/skills/associate`}>
              Associate skill
            </Link>
          </Button>
        }
      />

      {loading && (
        <div className="space-y-3" role="status" aria-label="Loading">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}

      <ApiErrorAlert error={error} className="mb-6" />

      {!loading && !error && (
        <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          {skills.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              No skills yet. Associate a catalog skill to configure this competition.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Skill</TableHead>
                  <TableHead className="hidden sm:table-cell">Details</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((s) => (
                  <TableRow key={s.skillId}>
                    <TableCell>
                      <Link
                        href={`/admin/competitions/${competitionId}/skills/${s.skillId}`}
                        className="font-semibold hover:underline"
                      >
                        {s.name}
                      </Link>
                      <p className="text-xs text-muted-foreground sm:hidden">
                        {[
                          s.familyName,
                          s.ageRule ? `Max age ${s.ageRule.maxAge}` : null,
                          s.capacity != null ? `Capacity ${s.capacity}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </p>
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">
                      {[
                        s.familyName,
                        s.ageRule ? `Max age ${s.ageRule.maxAge}` : null,
                        s.capacity != null ? `Capacity ${s.capacity}` : null,
                        s.hasPathway ? "Pathway set" : "Pathway missing",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        {s.active ? (
                          <Badge variant="success">Active</Badge>
                        ) : null}
                        <Button variant="link" className="h-auto px-0" asChild>
                          <Link
                            href={`/admin/competitions/${competitionId}/skills/${s.skillId}`}
                          >
                            Configure
                          </Link>
                        </Button>
                        <Button variant="link" className="h-auto px-0" asChild>
                          <Link
                            href={`/admin/competitions/${competitionId}/skills/${s.skillId}/pathway`}
                          >
                            Pathway
                          </Link>
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
    </PageShell>
  );
}
