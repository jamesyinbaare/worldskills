"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  CycleListItem,
  apiFetch,
  clearTokens,
  fetchMe,
  isAdminRole,
} from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function AdminCyclesPage() {
  const router = useRouter();
  const [cycles, setCycles] = useState<CycleListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMe();
        if (!isAdminRole(me.role)) {
          router.replace("/login");
          return;
        }
        const list = await apiFetch<CycleListItem[]>("/cycles");
        if (!cancelled) setCycles(list);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          clearTokens();
          router.replace("/login");
          return;
        }
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load cycles");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Competition cycles</h1>
          <p className="mt-1 text-muted-foreground">
            Configure DRAFT cycles, validate, and activate for a run.
          </p>
        </div>
        <Button asChild>
          <Link href="/admin/cycles/new">Create cycle</Link>
        </Button>
      </div>

      {loading && (
        <p className="mt-8 text-sm text-muted-foreground">Loading…</p>
      )}

      {error && (
        <Alert variant="destructive" className="mt-8">
          <AlertTitle>Could not load cycles</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!loading && !error && (
        <Card className="mt-8">
          <CardHeader>
            <CardTitle>All cycles</CardTitle>
            <CardDescription>
              Select a cycle to validate, activate, or clone.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-0 p-0">
            {cycles.length === 0 ? (
              <p className="px-6 py-8 text-sm text-muted-foreground">
                No cycles yet. Create the first competition cycle.
              </p>
            ) : (
              cycles.map((c, index) => (
                <div key={c.cycleId}>
                  {index > 0 && <Separator />}
                  <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
                    <div>
                      <Button variant="link" className="h-auto px-0 text-base font-semibold" asChild>
                        <Link href={`/admin/cycles/${c.cycleId}`}>{c.name}</Link>
                      </Button>
                      <p className="text-sm text-muted-foreground">
                        {c.period.start} → {c.period.end} · {c.timeZone}
                      </p>
                    </div>
                    <Badge variant="secondary">{c.status}</Badge>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
