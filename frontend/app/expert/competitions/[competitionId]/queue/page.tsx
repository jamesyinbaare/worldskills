"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  ApiError,
  fetchAssessorQueue,
  isChiefExpertRole,
  listMyAssignments,
  type MyAssignmentOut,
  type QueueSubmissionOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
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

function ExpertQueueContent() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const searchParams = useSearchParams();
  const router = useRouter();
  const skillIdParam = searchParams.get("skillId") ?? "";
  const { me, status } = useAuth();

  const [items, setItems] = useState<QueueSubmissionOut[]>([]);
  const [assignments, setAssignments] = useState<MyAssignmentOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated" || !me?.id) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [queue, mine] = await Promise.all([
          fetchAssessorQueue(me!.id, competitionId),
          listMyAssignments(),
        ]);
        if (cancelled) return;
        setItems(queue.items ?? queue.submissions ?? []);
        setAssignments(
          mine.filter((a) => a.competitionId === competitionId),
        );
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load assessor queue",
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
  }, [competitionId, me, status]);

  const competitionName = useMemo(() => {
    return assignments[0]?.competitionName ?? null;
  }, [assignments]);

  const skillOptions = useMemo(() => {
    const map = new Map<string, { skillId: string; label: string }>();
    for (const a of assignments) {
      const key = a.skillId;
      if (!map.has(key)) {
        map.set(key, {
          skillId: a.skillId,
          label: `${a.skillName} · ${a.zoneName}`,
        });
      } else {
        const existing = map.get(key)!;
        // Multiple zones for same skill — append zone if not already multi
        if (!existing.label.includes(a.zoneName)) {
          existing.label = `${a.skillName} · multiple zones`;
        }
      }
    }
    return Array.from(map.values());
  }, [assignments]);

  const selectedSkillLabel = useMemo(() => {
    if (!skillIdParam) return null;
    const match = assignments.find((a) => a.skillId === skillIdParam);
    if (!match) return null;
    const zones = assignments
      .filter((a) => a.skillId === skillIdParam)
      .map((a) => a.zoneName);
    const uniqueZones = Array.from(new Set(zones));
    return uniqueZones.length === 1
      ? `${match.skillName} · ${uniqueZones[0]}`
      : `${match.skillName} · ${uniqueZones.join(", ")}`;
  }, [assignments, skillIdParam]);

  function onSkillChange(nextSkillId: string | null) {
    if (!nextSkillId) return;
    const qs = new URLSearchParams(searchParams.toString());
    if (nextSkillId === "__all__") {
      qs.delete("skillId");
    } else {
      qs.set("skillId", nextSkillId);
    }
    const query = qs.toString();
    router.replace(
      query
        ? `/expert/competitions/${competitionId}/queue?${query}`
        : `/expert/competitions/${competitionId}/queue`,
    );
  }

  const canModerate = me?.role ? isChiefExpertRole(me.role) : false;

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title="Assessor queue"
        description="Submissions assigned to you for this competition. Open a row to score against the rubric."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {competitionName ?? "Competition"}
          </p>
          {selectedSkillLabel ? (
            <p className="text-sm text-muted-foreground">{selectedSkillLabel}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              All skills in your assignment for this competition
            </p>
          )}
        </div>

        {skillOptions.length > 0 ? (
          <div className="w-full space-y-2 sm:max-w-xs">
            <Label htmlFor="queue-skill">Skill focus</Label>
            <Select
              value={skillIdParam || "__all__"}
              onValueChange={onSkillChange}
            >
              <SelectTrigger
                id="queue-skill"
                className="min-h-11 w-full"
                data-testid="expert-queue-skill-select"
              >
                <SelectValue placeholder="All skills" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All skills</SelectItem>
                {skillOptions.map((opt) => (
                  <SelectItem key={opt.skillId} value={opt.skillId}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
      </div>

      <ApiErrorAlert error={error} />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading queue…
        </p>
      ) : null}

      <Card
        className="rounded-[1.5rem] border-border/70 shadow-sm"
        data-testid="expert-queue"
      >
        <CardHeader>
          <CardTitle className="text-lg">Assigned submissions</CardTitle>
          <CardDescription>
            {items.length === 0 && !loading
              ? "No submissions in your queue for this competition."
              : `${items.length} item(s)`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {items.length > 0 ? (
            <ul className="space-y-3">
              {items.map((item) => (
                <li
                  key={item.submissionId}
                  className="flex flex-col gap-2 rounded-2xl border border-border/70 bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
                  data-testid="expert-queue-item"
                >
                  <div>
                    <p className="font-medium" data-testid="expert-queue-anon">
                      {item.anonCode ?? "Anonymised submission"}
                    </p>
                    <div className="mt-2">
                      <StatusBadge status={item.state} />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild className="min-h-11 rounded-2xl">
                      <Link
                        href={`/expert/submissions/${item.submissionId}?from=${competitionId}`}
                        data-testid="expert-queue-score"
                      >
                        Score
                      </Link>
                    </Button>
                    {canModerate ? (
                      <Button
                        asChild
                        variant="outline"
                        className="min-h-11 rounded-2xl"
                      >
                        <Link
                          href={`/expert/submissions/${item.submissionId}/moderation`}
                          data-testid="expert-queue-moderate"
                        >
                          Moderate
                        </Link>
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </PageShell>
  );
}

export default function ExpertQueuePage() {
  return (
    <Suspense
      fallback={
        <PageShell width="wide">
          <p className="text-sm text-muted-foreground" role="status">
            Loading queue…
          </p>
        </PageShell>
      }
    >
      <ExpertQueueContent />
    </Suspense>
  );
}
