"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  CycleOut,
  apiFetch,
  clearTokens,
  fetchMe,
  isAdminRole,
} from "@/lib/api";
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

export default function NewCyclePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [timeZone, setTimeZone] = useState("Africa/Accra");
  const [languages, setLanguages] = useState("en");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const me = await fetchMe();
        if (!isAdminRole(me.role)) router.replace("/login");
      } catch {
        clearTokens();
        router.replace("/login");
      }
    })();
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const created = await apiFetch<CycleOut>("/cycles", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          period: { start, end },
          timeZone,
          organisingBody: { name: "CTVET" },
          branding: {},
          languages: languages
            .split(",")
            .map((l) => l.trim())
            .filter(Boolean),
        }),
      });
      router.push(`/admin/cycles/${created.cycleId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        const map: Record<string, string> = {};
        for (const f of err.fields) map[f.name] = f.reason;
        setFieldErrors(map);
      } else {
        setError("Could not create cycle");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-10 sm:px-6">
      <Button variant="link" className="mb-2 h-auto px-0" asChild>
        <Link href="/admin/cycles">← Cycles</Link>
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Create cycle</CardTitle>
          <CardDescription>
            Opens a DRAFT competition with its own isolated configuration.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                required
                minLength={3}
                maxLength={120}
                value={name}
                aria-invalid={Boolean(fieldErrors.name)}
                onChange={(e) => setName(e.target.value)}
              />
              {fieldErrors.name && (
                <p className="text-xs text-destructive">{fieldErrors.name}</p>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="start">Period start</Label>
                <Input
                  id="start"
                  type="date"
                  required
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="end">Period end</Label>
                <Input
                  id="end"
                  type="date"
                  required
                  value={end}
                  aria-invalid={Boolean(fieldErrors["period.end"])}
                  onChange={(e) => setEnd(e.target.value)}
                />
                {fieldErrors["period.end"] && (
                  <p className="text-xs text-destructive">
                    {fieldErrors["period.end"]}
                  </p>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tz">Time zone (IANA)</Label>
              <Input
                id="tz"
                required
                value={timeZone}
                aria-invalid={Boolean(fieldErrors.timeZone)}
                onChange={(e) => setTimeZone(e.target.value)}
              />
              {fieldErrors.timeZone && (
                <p className="text-xs text-destructive">{fieldErrors.timeZone}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="langs">Languages (comma-separated)</Label>
              <Input
                id="langs"
                required
                value={languages}
                onChange={(e) => setLanguages(e.target.value)}
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertTitle>Create failed</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Creating…" : "Create DRAFT cycle"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
