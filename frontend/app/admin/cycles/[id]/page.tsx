"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  CycleOut,
  ValidateOut,
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

export default function CycleWorkspacePage() {
  const params = useParams<{ id: string }>();
  const cycleId = params.id;
  const router = useRouter();
  const [cycle, setCycle] = useState<CycleOut | null>(null);
  const [validation, setValidation] = useState<ValidateOut | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await apiFetch<CycleOut>(`/cycles/${cycleId}`);
    setCycle(data);
  }, [cycleId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMe();
        if (!isAdminRole(me.role)) {
          router.replace("/login");
          return;
        }
        await load();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          clearTokens();
          router.replace("/login");
          return;
        }
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load cycle");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load, router]);

  async function runValidate() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<ValidateOut>(`/cycles/${cycleId}:validate`, {
        method: "POST",
      });
      setValidation(result);
      setMessage(result.ok ? "Validation passed." : "Validation found issues.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Validate failed");
    } finally {
      setBusy(false);
    }
  }

  async function runActivate() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<{ status: string }>(
        `/cycles/${cycleId}:activate`,
        { method: "POST" },
      );
      setMessage(`Cycle is ${result.status}.`);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError("Activate failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function runClone() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<{ newCycleId: string }>(
        `/cycles/${cycleId}:clone`,
        { method: "POST" },
      );
      router.push(`/admin/cycles/${result.newCycleId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Clone failed");
      setBusy(false);
    }
  }

  if (error && !cycle) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <Alert variant="destructive">
          <AlertTitle>Could not load cycle</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!cycle) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 text-muted-foreground">
        Loading workspace…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-6">
      <Button variant="link" className="h-auto px-0" asChild>
        <Link href="/admin/cycles">← Cycles</Link>
      </Button>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-2xl">{cycle.name || "Cycle"}</CardTitle>
            <CardDescription className="mt-1">
              {cycle.period?.start} → {cycle.period?.end} · {cycle.timeZone}
            </CardDescription>
          </div>
          <Badge variant="secondary">{cycle.status}</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" disabled={busy} onClick={runValidate}>
              Validate
            </Button>
            <Button disabled={busy} onClick={runActivate}>
              Activate
            </Button>
            <Button variant="accent" disabled={busy} onClick={runClone}>
              Clone
            </Button>
          </div>

          {message && (
            <Alert>
              <AlertTitle>Status</AlertTitle>
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          )}
          {error && (
            <Alert variant="destructive">
              <AlertTitle>Action failed</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {validation && (
        <Card>
          <CardHeader>
            <CardTitle>Validation issues</CardTitle>
            <CardDescription>
              {validation.ok
                ? "Configuration is complete."
                : "Fix the issues below before activation."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-0 p-0">
            {validation.ok ? (
              <p className="px-6 py-4 text-sm text-muted-foreground">No issues.</p>
            ) : (
              validation.issues.map((issue, idx) => (
                <div key={`${issue.entity}-${idx}`}>
                  {idx > 0 && <Separator />}
                  <div className="border-l-2 border-accent px-6 py-4">
                    <p className="text-sm font-medium">
                      {issue.code}: {issue.message}
                    </p>
                    <Button variant="link" className="h-auto px-0 text-xs" asChild>
                      <Link href={issue.link}>{issue.link}</Link>
                    </Button>
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
