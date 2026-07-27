"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  downloadSkillCriteriaDocument,
  getNominationQuotas,
  getPublicCompetition,
  listAvailableSkills,
  listInstitutionCompetitions,
  listInstitutionRegistrations,
  triggerBrowserDownload,
  type AvailableSkillOut,
  type InstitutionCompetitionOut,
  type InstitutionRegistrationOut,
  type NominationQuotaOut,
} from "@/lib/api";
import { InstitutionSkillCard } from "@/components/institution/InstitutionSkillCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type SkillRow = {
  skillId: string;
  skillName: string;
  familyName?: string | null;
  number?: string | null;
  quota: NominationQuotaOut | null;
  hasCriteriaDocument?: boolean;
};

export default function InstitutionCompetitionPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;

  const [competition, setCompetition] = useState<InstitutionCompetitionOut | null>(
    null,
  );
  const [skills, setSkills] = useState<AvailableSkillOut[]>([]);
  const [quotas, setQuotas] = useState<NominationQuotaOut[]>([]);
  const [roster, setRoster] = useState<InstitutionRegistrationOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [criteriaPendingId, setCriteriaPendingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const [available, q, regs, competitions] = await Promise.all([
          listAvailableSkills(competitionId),
          getNominationQuotas(competitionId),
          listInstitutionRegistrations(),
          listInstitutionCompetitions(),
        ]);
        if (cancelled) return;

        const filteredRoster = regs.filter(
          (r) => r.competitionId === competitionId,
        );
        const matchingCompetition =
          competitions.find((row) => row.competitionId === competitionId) ?? null;
        setSkills(available.filter((s) => s.active));
        setQuotas(q.quotas);
        setRoster(filteredRoster);
        setCompetition(matchingCompetition);
        setError(null);

        let name: string | null = filteredRoster[0]?.competitionName ?? null;
        try {
          const pub = await getPublicCompetition(competitionId);
          if (!cancelled && pub.name) name = pub.name;
        } catch {
          /* public profile optional when window closed */
        }
        if (!cancelled && matchingCompetition === null && name) {
          setCompetition({
            competitionId,
            name,
            status: filteredRoster[0]?.competitionStatus ?? "UNKNOWN",
            period: { start: "", end: "" },
            description: null,
            window: null,
          });
        }
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

  const skillRows: SkillRow[] = useMemo(() => {
    const quotaBySkill = new Map(quotas.map((q) => [q.skillId, q]));
    const fromSkills = skills.map((s) => ({
      skillId: s.skillId,
      skillName: s.name,
      familyName: s.familyName,
      number: s.number,
      quota: quotaBySkill.get(s.skillId) ?? null,
      hasCriteriaDocument: Boolean(s.hasCriteriaDocument),
    }));
    if (fromSkills.length > 0) return fromSkills;

    return quotas.map((q) => ({
      skillId: q.skillId,
      skillName: q.skillName,
      familyName: null,
      number: null,
      quota: q,
      hasCriteriaDocument: false,
    }));
  }, [skills, quotas]);

  const competitionName = competition?.name ?? "Competition";
  const registrationEnabled = competition?.status === "ACTIVE";

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title={competitionName}
        description={
          registrationEnabled
            ? "Select a skill area to register a student. Quotas apply per skill for your school."
            : "This competition is view-only right now. Skill areas and roster are still available for reference."
        }
        backHref="/institution/competitions"
      />

      <ApiErrorAlert error={error} title="Could not load competition" />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : null}

      {competition ? (
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={competition.status} />
          {competition.description ? (
            <p className="text-sm text-muted-foreground">
              {competition.description}
            </p>
          ) : null}
        </div>
      ) : null}

      <section className="space-y-3" data-testid="institution-skill-areas">
        <h2 className="text-lg font-semibold">Skill areas</h2>

        {skillRows.length === 0 && !loading ? (
          <Card>
            <CardContent className="py-6 text-sm text-muted-foreground">
              No skill areas are available yet. Contact the Secretariat if you
              expected registration slots.
            </CardContent>
          </Card>
        ) : (
          <ul
            className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3"
            data-testid="institution-quotas"
          >
            {skillRows.map((row, index) => (
              <li key={row.skillId}>
                <InstitutionSkillCard
                  competitionId={competitionId}
                  skillId={row.skillId}
                  skillName={row.skillName}
                  familyName={row.familyName}
                  number={row.number}
                  quota={row.quota}
                  registrationEnabled={registrationEnabled}
                  disabledLabel={
                    registrationEnabled ? "Quota full" : "Registration closed"
                  }
                  index={index}
                  hasCriteriaDocument={row.hasCriteriaDocument}
                  criteriaDownloadPending={criteriaPendingId === row.skillId}
                  onDownloadCriteria={() => {
                    void (async () => {
                      setCriteriaPendingId(row.skillId);
                      setError(null);
                      try {
                        const { blob, filename } =
                          await downloadSkillCriteriaDocument(
                            competitionId,
                            row.skillId,
                          );
                        triggerBrowserDownload(blob, filename);
                      } catch (err) {
                        if (err instanceof ApiError) setError(err);
                      } finally {
                        setCriteriaPendingId(null);
                      }
                    })();
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3" data-testid="institution-competition-roster">
        <h2 className="text-lg font-semibold">Roster</h2>
        {roster.length === 0 && !loading ? (
          <Card className="border-dashed">
            <CardContent className="py-8 text-sm text-muted-foreground sm:text-center">
              No registrations yet. Choose a skill area above to add the first
              competitor.
            </CardContent>
          </Card>
        ) : null}
        <ul className="space-y-2">
          {roster.map((row) => {
            const name =
              [row.givenNames, row.familyName].filter(Boolean).join(" ") ||
              row.competitorRef;
            return (
              <li key={row.competitorId}>
                <Card>
                  <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 space-y-1">
                      <p className="truncate font-medium">{name}</p>
                      <p className="text-sm text-muted-foreground">
                        {row.skillName}
                        {row.gender ? ` · ${row.gender}` : ""}
                      </p>
                      <p className="font-mono text-xs text-muted-foreground">
                        {row.competitorRef}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={row.status} />
                      <Button variant="outline" className="min-h-11" asChild>
                        <Link
                          href={`/institution/competitors/${row.competitorId}/lifecycle`}
                        >
                          Withdraw
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
    </PageShell>
  );
}
