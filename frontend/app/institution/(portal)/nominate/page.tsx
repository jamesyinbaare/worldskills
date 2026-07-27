"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRightIcon,
  TrophyIcon,
} from "lucide-react";
import {
  ApiError,
  getNominationQuotas,
  listInstitutionRegistrations,
  listOpenCompetitions,
  type InstitutionRegistrationOut,
  type OpenCompetitionOut,
} from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type QuotaHint = { remaining: number; configured: boolean; max: number };

function formatWindow(window?: { opensAt: string; closesAt: string } | null): string | null {
  if (!window?.closesAt) return null;
  try {
    const closes = new Date(window.closesAt);
    if (Number.isNaN(closes.getTime())) return null;
    return `Registration closes ${closes.toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    })}`;
  } catch {
    return null;
  }
}

export default function InstitutionNominatePage() {
  const [openCycles, setOpenCycles] = useState<OpenCompetitionOut[]>([]);
  const [roster, setRoster] = useState<InstitutionRegistrationOut[]>([]);
  const [quotaHints, setQuotaHints] = useState<Record<string, QuotaHint>>({});
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const [cycles, regs] = await Promise.all([
          listOpenCompetitions(),
          listInstitutionRegistrations(),
        ]);
        if (cancelled) return;
        setOpenCycles(cycles);
        setRoster(regs);
        setLoadError(null);

        const ids = new Set([
          ...cycles.map((c) => c.competitionId),
          ...regs.map((r) => r.competitionId),
        ]);
        const hints: Record<string, QuotaHint> = {};
        await Promise.all(
          [...ids].slice(0, 10).map(async (id) => {
            try {
              const q = await getNominationQuotas(id);
              const configured = q.quotas.filter((row) => row.configured);
              hints[id] = {
                remaining: configured.reduce((s, r) => s + r.remaining, 0),
                max: configured.reduce((s, r) => s + r.max, 0),
                configured: configured.length > 0,
              };
            } catch {
              /* optional */
            }
          }),
        );
        if (!cancelled) setQuotaHints(hints);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setLoadError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const rosterCompetitions = (() => {
    const map = new Map<string, { name: string; count: number }>();
    for (const row of roster) {
      const cur = map.get(row.competitionId);
      if (cur) cur.count += 1;
      else map.set(row.competitionId, { name: row.competitionName, count: 1 });
    }
    return [...map.entries()].map(([id, v]) => ({
      competitionId: id,
      competitionName: v.name,
      count: v.count,
    }));
  })();

  const openIds = new Set(openCycles.map((c) => c.competitionId));
  const continueList = rosterCompetitions.filter(
    (c) => !openIds.has(c.competitionId),
  );

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title="Register a competitor"
        description="Pick an open competition to see skill areas and register a student."
        backHref="/institution"
        backLabel="Dashboard"
      />

      <ApiErrorAlert error={loadError} title="Could not load competitions" />

      <section className="space-y-4" data-testid="nominate-competition-list">
        <h2 className="text-lg font-semibold">Open competitions</h2>
        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading…
          </p>
        ) : null}
        {!loading && openCycles.length === 0 ? (
          <Card>
            <CardContent className="space-y-2 py-8">
              <p className="font-medium">Nothing open for registration</p>
              <p className="text-sm text-muted-foreground">
                When the Secretariat opens registration, competitions appear
                here. You can continue with a competition your school already
                uses below, if any.
              </p>
            </CardContent>
          </Card>
        ) : null}

        <ul className="space-y-3">
          {openCycles.map((c) => {
            const hint = quotaHints[c.competitionId];
            const skillsHref = `/institution/competitions/${c.competitionId}`;
            return (
              <li key={c.competitionId}>
                <Card className="overflow-hidden border-border/80 shadow-sm">
                  <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
                        <TrophyIcon className="size-5" aria-hidden />
                      </span>
                      <div className="min-w-0 space-y-1">
                        <h3 className="text-base font-semibold leading-snug">
                          {c.name}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {formatWindow(c.window) ?? "Registration window open"}
                          {hint?.configured
                            ? ` · ${hint.remaining} of ${hint.max} slots left`
                            : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                      <Button
                        size="lg"
                        className="min-h-12 w-full gap-2 sm:min-w-[11rem]"
                        asChild
                      >
                        <Link
                          href={skillsHref}
                          data-testid={`nominate-pick-${c.competitionId}`}
                        >
                          View skill areas
                          <ArrowRightIcon className="size-4 opacity-70" aria-hidden />
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      </section>

      {continueList.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Your school’s competitions</h2>
          <p className="text-sm text-muted-foreground">
            Competitions where you already have registrations.
          </p>
          <ul className="space-y-2">
            {continueList.map((c) => (
              <li key={c.competitionId}>
                <Card>
                  <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="font-medium">{c.competitionName}</p>
                      <p className="text-sm text-muted-foreground">
                        {c.count} on roster
                        {quotaHints[c.competitionId]?.configured
                          ? ` · ${quotaHints[c.competitionId].remaining} slots left`
                          : ""}
                      </p>
                    </div>
                    <Button className="min-h-11 gap-2" asChild>
                      <Link
                        href={`/institution/competitions/${c.competitionId}`}
                      >
                        View skill areas
                      </Link>
                    </Button>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </PageShell>
  );
}
