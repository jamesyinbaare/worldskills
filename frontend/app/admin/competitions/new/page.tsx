"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, CompetitionOut, apiFetch } from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function NewCompetitionPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [timeZone, setTimeZone] = useState("Africa/Accra");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const created = await apiFetch<CompetitionOut>("/competitions", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          period: { start, end },
          timeZone,
          description: description.trim() || null,
          organisingBody: { name: "CTVET" },
          branding: {},
          languages: ["en"],
        }),
      });
      router.push(`/admin/competitions/${created.competitionId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not create competition",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="narrow">
      <PageHeader
        title="Create competition"
        description="Opens a DRAFT competition with its own isolated configuration."
        backHref="/admin/competitions"
        backLabel="Competitions"
      />

      <Card>
        <CardHeader>
          <CardDescription>
            Drafts stay inactive until validation and activation succeed.
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
                className="min-h-11"
                value={name}
                aria-invalid={Boolean(fieldErrors.name)}
                aria-describedby={
                  fieldErrors.name ? "name-error" : undefined
                }
                onChange={(e) => setName(e.target.value)}
              />
              <FieldMessage id="name-error" message={fieldErrors.name} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="start">Period start</Label>
                <Input
                  id="start"
                  type="date"
                  required
                  className="min-h-11"
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
                  className="min-h-11"
                  value={end}
                  aria-invalid={Boolean(fieldErrors["period.end"])}
                  aria-describedby={
                    fieldErrors["period.end"] ? "period-end-error" : undefined
                  }
                  onChange={(e) => setEnd(e.target.value)}
                />
                <FieldMessage
                  id="period-end-error"
                  message={fieldErrors["period.end"]}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tz">Time zone (IANA)</Label>
              <Input
                id="tz"
                required
                className="min-h-11"
                value={timeZone}
                aria-invalid={Boolean(fieldErrors.timeZone)}
                aria-describedby={
                  fieldErrors.timeZone ? "tz-error" : undefined
                }
                onChange={(e) => setTimeZone(e.target.value)}
              />
              <FieldMessage id="tz-error" message={fieldErrors.timeZone} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">About this competition</Label>
              <Textarea
                id="description"
                className="min-h-28"
                value={description}
                maxLength={20000}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional public description shown while the competition is active."
              />
            </div>
            <ApiErrorAlert error={error} />
            <Button type="submit" disabled={pending} className="min-h-11">
              {pending ? "Creating…" : "Create DRAFT competition"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
