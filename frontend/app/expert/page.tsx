"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  listMyAssignments,
  type MyAssignmentOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ClipboardListIcon } from "lucide-react";

export default function ExpertHomePage() {
  const router = useRouter();
  const [assignments, setAssignments] = useState<MyAssignmentOut[] | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [competitionId, setCompetitionId] = useState("");
  const [assignmentKey, setAssignmentKey] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyAssignments();
        if (cancelled) return;
        setAssignments(rows);
        setError(null);
        if (rows.length > 0) {
          setCompetitionId(rows[0].competitionId);
          setAssignmentKey(
            `${rows[0].skillId}:${rows[0].zoneId}:${rows[0].assignmentId}`,
          );
        }
      } catch (err) {
        if (!cancelled) {
          setAssignments([]);
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load your assignments",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const competitions = useMemo(() => {
    if (!assignments) return [];
    const map = new Map<string, string>();
    for (const a of assignments) {
      if (!map.has(a.competitionId)) {
        map.set(a.competitionId, a.competitionName);
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [assignments]);

  const skillOptions = useMemo(() => {
    if (!assignments || !competitionId) return [];
    return assignments.filter((a) => a.competitionId === competitionId);
  }, [assignments, competitionId]);

  useEffect(() => {
    if (skillOptions.length === 0) {
      setAssignmentKey("");
      return;
    }
    const stillValid = skillOptions.some(
      (a) =>
        `${a.skillId}:${a.zoneId}:${a.assignmentId}` === assignmentKey,
    );
    if (!stillValid) {
      const first = skillOptions[0];
      setAssignmentKey(
        `${first.skillId}:${first.zoneId}:${first.assignmentId}`,
      );
    }
  }, [skillOptions, assignmentKey]);

  function onOpenQueue(e: FormEvent) {
    e.preventDefault();
    if (!competitionId || !assignmentKey) return;
    const selected = skillOptions.find(
      (a) =>
        `${a.skillId}:${a.zoneId}:${a.assignmentId}` === assignmentKey,
    );
    if (!selected) return;
    const qs = new URLSearchParams({ skillId: selected.skillId });
    router.push(
      `/expert/competitions/${competitionId}/queue?${qs.toString()}`,
    );
  }

  const loading = assignments === null;

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title="Assessor portal"
        description="Open your conflict-filtered scoring queue for an assigned competition and skill, then enter rubric marks in blind mode when configured."
      />

      <ApiErrorAlert error={error} />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading your assignments…
        </p>
      ) : null}

      {!loading && assignments.length === 0 && !error ? (
        <Card className="rounded-[1.5rem] border-border/70 shadow-sm">
          <CardContent className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <ClipboardListIcon className="h-10 w-10 text-muted-foreground/60" />
            <div className="space-y-1">
              <p className="text-base font-semibold">No scoring assignments</p>
              <p className="max-w-md text-sm text-muted-foreground">
                You have no scoring assignments yet. An administrator must
                assign you to a competition skill and zone before you can open
                a queue.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!loading && assignments.length > 0 ? (
        <>
          <Card className="rounded-[1.5rem] border-border/70 shadow-sm">
            <CardHeader>
              <CardTitle className="text-lg">Quick open</CardTitle>
              <CardDescription>
                Choose a competition and skill from your assignments — no IDs to
                remember.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={onOpenQueue} className="space-y-4" noValidate>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="competitionId">Competition</Label>
                    <Select
                      value={competitionId}
                      onValueChange={(value) => {
                        if (value) setCompetitionId(value);
                      }}
                    >
                      <SelectTrigger
                        id="competitionId"
                        className="min-h-11 w-full"
                        data-testid="expert-competition-select"
                      >
                        <SelectValue placeholder="Select competition" />
                      </SelectTrigger>
                      <SelectContent>
                        {competitions.map((c) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="skillId">Skill</Label>
                    <Select
                      value={assignmentKey}
                      onValueChange={(value) => {
                        if (value) setAssignmentKey(value);
                      }}
                      disabled={skillOptions.length === 0}
                    >
                      <SelectTrigger
                        id="skillId"
                        className="min-h-11 w-full"
                        data-testid="expert-skill-select"
                      >
                        <SelectValue placeholder="Select skill" />
                      </SelectTrigger>
                      <SelectContent>
                        {skillOptions.map((a) => (
                          <SelectItem
                            key={a.assignmentId}
                            value={`${a.skillId}:${a.zoneId}:${a.assignmentId}`}
                          >
                            {a.skillName} · {a.zoneName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <Button
                  type="submit"
                  className="min-h-11 rounded-2xl"
                  disabled={!competitionId || !assignmentKey}
                  data-testid="expert-open-queue"
                >
                  Open queue
                </Button>
              </form>
            </CardContent>
          </Card>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              My assignments
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {assignments.map((a) => (
                <li key={a.assignmentId}>
                  <Card
                    className="h-full rounded-[1.5rem] border-border/70 shadow-sm"
                    data-testid="expert-assignment-card"
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">
                        {a.competitionName}
                      </CardTitle>
                      <CardDescription>
                        {a.skillName} · {a.zoneName}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button
                        asChild
                        className="min-h-11 w-full rounded-2xl"
                        variant="outline"
                      >
                        <Link
                          href={`/expert/competitions/${a.competitionId}/queue?skillId=${encodeURIComponent(a.skillId)}`}
                          data-testid="expert-assignment-open-queue"
                        >
                          Open queue
                        </Link>
                      </Button>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </PageShell>
  );
}
