"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  fetchSkillProgression,
  type SkillProgressionOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function ProgressionBody({
  competitionId,
  skillId,
}: {
  competitionId: string;
  skillId: string;
}) {
  const [data, setData] = useState<SkillProgressionOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const out = await fetchSkillProgression(competitionId, skillId);
        if (!cancelled) setData(out);
      } catch (err) {
        if (!cancelled) {
          setData(null);
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load progression",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [competitionId, skillId]);

  return (
    <>
      <ApiErrorAlert error={error} />
      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading progression…
        </p>
      ) : null}
      {data ? (
        <div className="space-y-6" data-testid="progression-panel">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{data.skillName}</CardTitle>
              <CardDescription>
                Skill <span className="font-mono text-xs">{data.skillId}</span>
              </CardDescription>
            </CardHeader>
          </Card>

          {data.byZone.map((zone) => (
            <Card key={zone.zoneId} data-testid="progression-zone">
              <CardHeader>
                <CardTitle className="text-base">{zone.zoneName}</CardTitle>
                <CardDescription>
                  Zone <span className="font-mono text-xs">{zone.zoneId}</span>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-3">
                  {zone.stages.map((st) => {
                    const released = st.status === "RELEASED";
                    return (
                      <li
                        key={st.stageId}
                        className="rounded-md border border-border p-3"
                        data-testid="progression-stage"
                        data-status={st.status}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">
                            {st.order}. {st.stage}
                          </span>
                          <StatusBadge
                            status={st.status}
                            label={
                              released ? "Released" : "In progress"
                            }
                          />
                        </div>
                        {released && st.counts ? (
                          <dl
                            className="mt-2 grid grid-cols-3 gap-2 text-sm"
                            data-testid="progression-counts"
                          >
                            <div>
                              <dt className="text-muted-foreground">Advanced</dt>
                              <dd>{st.counts.advanced}</dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">Waitlisted</dt>
                              <dd>{st.counts.waitlisted}</dd>
                            </div>
                            <div>
                              <dt className="text-muted-foreground">Excluded</dt>
                              <dd>{st.counts.excluded}</dd>
                            </div>
                          </dl>
                        ) : (
                          <Alert className="mt-2" data-testid="progression-embargo">
                            <AlertTitle>Embargoed</AlertTitle>
                            <AlertDescription>
                              Outcomes for this stage are not public yet. Only a
                              neutral in-progress status is shown.
                            </AlertDescription>
                          </Alert>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </>
  );
}

export default function SkillProgressionPage() {
  const params = useParams<{ competitionId: string; skillId: string }>();
  const competitionId = params.competitionId;
  const skillId = params.skillId;
  const router = useRouter();
  const [lookupSkill, setLookupSkill] = useState(skillId || "");

  function onLookup(e: FormEvent) {
    e.preventDefault();
    const sk = lookupSkill.trim();
    if (!sk) return;
    router.push(`/directory/${competitionId}/skills/${sk}/progression`);
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Skill progression"
        description="Per-zone stage pipeline. Embargoed stages show only a neutral status — never scores or rankings."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Skill</CardTitle>
          <CardDescription>
            Competition <span className="font-mono text-xs">{competitionId}</span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={onLookup}
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
          >
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="skillLookup">Skill ID</Label>
              <Input
                id="skillLookup"
                className="min-h-11"
                value={lookupSkill}
                onChange={(e) => setLookupSkill(e.target.value)}
                data-testid="progression-skill-id"
              />
            </div>
            <Button type="submit" className="min-h-11" data-testid="progression-go">
              View
            </Button>
          </form>
        </CardContent>
      </Card>

      {skillId ? (
        <ProgressionBody competitionId={competitionId} skillId={skillId} />
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link
          href={`/directory/${competitionId}`}
          className="underline underline-offset-2"
        >
          Back to directory
        </Link>
        {" · "}
        <Link href="/" className="underline underline-offset-2">
          Home
        </Link>
      </p>
    </PageShell>
  );
}
