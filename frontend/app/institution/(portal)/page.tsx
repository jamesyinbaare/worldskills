"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SearchIcon } from "lucide-react";
import {
  ApiError,
  listInstitutionRegistrations,
  type InstitutionRegistrationOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function displayName(row: InstitutionRegistrationOut): string {
  const name = [row.givenNames, row.familyName].filter(Boolean).join(" ");
  return name || row.competitorRef;
}

function searchText(row: InstitutionRegistrationOut): string {
  return [
    displayName(row),
    row.competitorRef,
    row.skillName,
    row.competitionName,
    row.status,
  ]
    .join(" ")
    .toLowerCase();
}

export default function InstitutionDashboardPage() {
  const [registrations, setRegistrations] = useState<InstitutionRegistrationOut[]>(
    [],
  );
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [competitionFilter, setCompetitionFilter] = useState("all");
  const [skillFilter, setSkillFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const roster = await listInstitutionRegistrations();
        if (cancelled) return;
        setRegistrations(roster);
        setLoadError(null);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setLoadError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeRegistrations = useMemo(
    () =>
      registrations.filter((row) =>
        ["ACTIVE", "LOCKED"].includes(row.competitionStatus),
      ),
    [registrations],
  );

  const competitionOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of activeRegistrations) {
      map.set(row.competitionId, row.competitionName);
    }
    return [...map.entries()]
      .map(([competitionId, competitionName]) => ({
        competitionId,
        competitionName,
      }))
      .sort((a, b) => a.competitionName.localeCompare(b.competitionName));
  }, [activeRegistrations]);

  const skillOptions = useMemo(
    () =>
      [...new Set(activeRegistrations.map((row) => row.skillName))].sort((a, b) =>
        a.localeCompare(b),
      ),
    [activeRegistrations],
  );

  const statusOptions = useMemo(
    () =>
      [...new Set(activeRegistrations.map((row) => row.status))].sort((a, b) =>
        a.localeCompare(b),
      ),
    [activeRegistrations],
  );

  const filteredRegistrations = useMemo(() => {
    const query = search.trim().toLowerCase();
    return activeRegistrations.filter((row) => {
      if (competitionFilter !== "all" && row.competitionId !== competitionFilter) {
        return false;
      }
      if (skillFilter !== "all" && row.skillName !== skillFilter) {
        return false;
      }
      if (statusFilter !== "all" && row.status !== statusFilter) {
        return false;
      }
      if (query && !searchText(row).includes(query)) {
        return false;
      }
      return true;
    });
  }, [activeRegistrations, competitionFilter, search, skillFilter, statusFilter]);

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title="School dashboard"
        description="Track competitors in current competitions and jump straight into their lifecycle details."
      />

      <ApiErrorAlert error={loadError} title="Could not load dashboard" />

      <section className="space-y-4" data-testid="institution-roster">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Active competitors</h2>
            <p className="text-sm text-muted-foreground">
              Only competitors attached to current competitions appear here.
            </p>
          </div>
          <p className="text-sm text-muted-foreground">
            {filteredRegistrations.length} competitor
            {filteredRegistrations.length === 1 ? "" : "s"}
          </p>
        </div>

        <Card>
          <CardContent className="grid gap-3 py-4 md:grid-cols-[minmax(0,2fr),1fr,1fr,1fr]">
            <label className="relative block">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search competitor, ref, skill, or competition"
                className="h-11 pl-9"
                data-testid="institution-overview-search"
              />
            </label>

            <Select value={competitionFilter} onValueChange={setCompetitionFilter}>
              <SelectTrigger className="h-11 w-full" data-testid="institution-overview-competition-filter">
                <SelectValue placeholder="All competitions" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All competitions</SelectItem>
                {competitionOptions.map((item) => (
                  <SelectItem key={item.competitionId} value={item.competitionId}>
                    {item.competitionName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={skillFilter} onValueChange={setSkillFilter}>
              <SelectTrigger className="h-11 w-full" data-testid="institution-overview-skill-filter">
                <SelectValue placeholder="All skill areas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All skill areas</SelectItem>
                {skillOptions.map((skill) => (
                  <SelectItem key={skill} value={skill}>
                    {skill}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-11 w-full" data-testid="institution-overview-status-filter">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {statusOptions.map((status) => (
                  <SelectItem key={status} value={status}>
                    {status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading competitors…
          </p>
        ) : null}

        {!loading && activeRegistrations.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="space-y-3 py-8 text-sm text-muted-foreground sm:text-center">
              <p>No competitors are attached to active competitions yet.</p>
              <p>
                Browse the{" "}
                <Link href="/institution/competitions" className="font-medium text-foreground underline underline-offset-2">
                  competitions catalog
                </Link>{" "}
                to register students for available skill areas.
              </p>
            </CardContent>
          </Card>
        ) : null}

        {!loading && activeRegistrations.length > 0 && filteredRegistrations.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-8 text-sm text-muted-foreground sm:text-center">
              No active competitors match your search or filters.
            </CardContent>
          </Card>
        ) : null}

        <ul className="space-y-2">
          {filteredRegistrations.map((row) => (
            <li key={row.competitorId}>
              <Link
                href={`/institution/competitors/${row.competitorId}/lifecycle`}
                data-testid={`institution-competitor-${row.competitorId}`}
                className="block"
              >
                <Card className="transition-shadow hover:shadow-md">
                  <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 space-y-1">
                      <p className="truncate font-medium">{displayName(row)}</p>
                      <p className="text-sm text-muted-foreground">
                        {row.competitionName} · {row.skillName}
                        {row.gender ? ` · ${row.gender}` : ""}
                      </p>
                      <p className="font-mono text-xs text-muted-foreground">
                        {row.competitorRef}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={row.status} />
                      <span className="text-sm font-medium text-foreground">
                        View details
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </PageShell>
  );
}
