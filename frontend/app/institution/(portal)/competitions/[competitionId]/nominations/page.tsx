"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  loadNominations,
  type NominationRow,
} from "@/lib/nominationStore";

export default function InstitutionNominationsPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [rows] = useState<NominationRow[]>(() => loadNominations(competitionId));

  return (
    <PageShell>
      <PageHeader
        title="Nominations"
        description="Track nomination status for this competition."
        backHref="/institution"
        backLabel="Institution home"
        actions={
          <Button className="min-h-11 shrink-0" asChild>
            <Link href={`/institution/competitions/${competitionId}/nominations/new`}>
              New nomination
            </Link>
          </Button>
        }
      />

      <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
        <div className="border-b border-border px-4 py-3 sm:px-6">
          <p className="text-sm text-muted-foreground">
            {rows.length === 0
              ? "No nominations yet. Submit the first nomination for this competition."
              : `${rows.length} nomination(s)`}
          </p>
        </div>
        <ul
          className="divide-y divide-border"
          data-testid="nomination-list"
          aria-live="polite"
        >
          {rows.map((row) => (
            <li
              key={row.nominationId}
              data-testid="nomination-row"
              data-status={row.status}
              className="px-4 py-4 sm:px-6"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium break-all">
                  {row.competitorRef ?? row.nominationId}
                </p>
                <StatusBadge status={row.status} />
              </div>
              {row.skillId ? (
                <p className="mt-1 text-xs text-muted-foreground break-all">
                  Skill ID: {row.skillId}
                </p>
              ) : null}
              {row.reason ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Reason: {row.reason}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </PageShell>
  );
}
