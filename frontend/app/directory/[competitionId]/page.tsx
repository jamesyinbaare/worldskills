"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  fetchPublicDirectory,
  type PublicCompetitorListItem,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function PublicDirectoryPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const router = useRouter();

  const [skill, setSkill] = useState("");
  const [zone, setZone] = useState("");
  const [items, setItems] = useState<PublicCompetitorListItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  async function load(cursor?: string | null, append = false) {
    setLoading(true);
    setError(null);
    try {
      const out = await fetchPublicDirectory(competitionId, {
        skill: skill.trim() || null,
        zone: zone.trim() || null,
        cursor: cursor || null,
        limit: 20,
      });
      setItems((prev) => (append ? [...prev, ...out.items] : out.items));
      setNextCursor(out.nextCursor ?? null);
    } catch (err) {
      if (!append) setItems([]);
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not load directory",
                fields: [],
                traceId: "",
              },
            }),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(null, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial + cycle change
  }, [competitionId]);

  function onFilter(e: FormEvent) {
    e.preventDefault();
    const qs = new URLSearchParams();
    if (skill.trim()) qs.set("skill", skill.trim());
    if (zone.trim()) qs.set("zone", zone.trim());
    const q = qs.toString();
    router.replace(`/directory/${competitionId}${q ? `?${q}` : ""}`);
    void load(null, false);
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Competitor directory"
        description="Public listing of consented competitors. Only fields returned by the API are shown."
      />

      <ApiErrorAlert error={error} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Filters</CardTitle>
          <CardDescription>
            Competition <span className="font-mono text-xs">{competitionId}</span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={onFilter}
            className="space-y-4"
            noValidate
            data-testid="directory-filters"
          >
            <div className="space-y-2">
              <Label htmlFor="skill">Skill ID (optional)</Label>
              <Input
                id="skill"
                className="min-h-11"
                value={skill}
                onChange={(e) => setSkill(e.target.value)}
                data-testid="directory-skill"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="zone">Zone ID (optional)</Label>
              <Input
                id="zone"
                className="min-h-11"
                value={zone}
                onChange={(e) => setZone(e.target.value)}
                data-testid="directory-zone"
              />
            </div>
            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={loading}
              data-testid="directory-apply"
            >
              Apply filters
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card data-testid="directory-list">
        <CardHeader>
          <CardTitle className="text-lg">Competitors</CardTitle>
          <CardDescription>
            {loading ? "Loading…" : `${items.length} shown`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {items.length === 0 && !loading ? (
            <p className="text-sm text-muted-foreground" data-testid="directory-empty">
              No public competitors for this competition and filter.
            </p>
          ) : (
            <ul className="space-y-3">
              {items.map((item) => (
                <li
                  key={item.competitorId}
                  className="rounded-md border border-border p-3"
                  data-testid="directory-item"
                >
                  <Link
                    href={`/directory/competitors/${item.competitorId}`}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {item.displayName ?? item.competitorId}
                  </Link>
                  <div className="mt-2 flex flex-wrap gap-2 text-sm text-muted-foreground">
                    {item.skill ? <span>{item.skill}</span> : null}
                    {item.zone ? <span>· {item.zone}</span> : null}
                    {item.institution ? <span>· {item.institution}</span> : null}
                    {item.stageStatus ? (
                      <StatusBadge status={item.stageStatus} />
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {nextCursor ? (
            <Button
              type="button"
              variant="outline"
              className="mt-4 min-h-11 w-full"
              disabled={loading}
              onClick={() => void load(nextCursor, true)}
              data-testid="directory-more"
            >
              Load more
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Skill progression</CardTitle>
          <CardDescription>
            View the embargo-aware stage pipeline for a skill in this competition.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const sk = skill.trim();
              if (!sk) return;
              router.push(`/directory/${competitionId}/skills/${sk}/progression`);
            }}
            className="space-y-4"
            noValidate
          >
            <p className="text-sm text-muted-foreground">
              Enter a skill ID (use the filter field above or paste an ID), then
              open progression.
            </p>
            <Button
              type="submit"
              variant="secondary"
              className="min-h-11 w-full"
              disabled={!skill.trim()}
              data-testid="directory-open-progression"
            >
              Open progression for filtered skill
            </Button>
          </form>
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        <Link href="/" className="underline underline-offset-2">
          Back to home
        </Link>
      </p>
    </PageShell>
  );
}
