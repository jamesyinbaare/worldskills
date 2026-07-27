"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  getCompetitionSchoolQuotas,
  upsertCompetitionSchoolQuotas,
  type NominationQuotaOut,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AdminSchoolQuotasPage() {
  const params = useParams<{ id: string }>();
  const competitionId = params.id;

  const [quotas, setQuotas] = useState<NominationQuotaOut[]>([]);
  const [maxBySkill, setMaxBySkill] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const out = await getCompetitionSchoolQuotas(competitionId);
    setQuotas(out.quotas);
    const next: Record<string, string> = {};
    for (const row of out.quotas) {
      next[row.skillId] = row.configured ? String(row.max) : "";
    }
    setMaxBySkill(next);
  }, [competitionId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        await reload();
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSavedMessage(null);
    setError(null);
    setFieldErrors({});

    const payloadLimits: { skillId: string; maxNominations: number }[] = [];
    for (const row of quotas) {
      const raw = (maxBySkill[row.skillId] ?? "").trim();
      if (raw === "") continue;
      const maxNominations = Number(raw);
      if (
        !Number.isInteger(maxNominations) ||
        maxNominations < 0 ||
        maxNominations > 1000
      ) {
        setFieldErrors({
          [`max-${row.skillId}`]: "Enter a whole number from 0 to 1000",
        });
        return;
      }
      payloadLimits.push({ skillId: row.skillId, maxNominations });
    }

    if (payloadLimits.length === 0) {
      setFieldErrors({ limits: "Set at least one skill quota" });
      return;
    }

    setPending(true);
    try {
      const out = await upsertCompetitionSchoolQuotas(competitionId, {
        limits: payloadLimits,
      });
      setQuotas(out.quotas);
      const next: Record<string, string> = {};
      for (const row of out.quotas) {
        next[row.skillId] = row.configured ? String(row.max) : "";
      }
      setMaxBySkill(next);
      setSavedMessage(
        "School quotas saved. These limits apply to every school for each skill area.",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title="School quotas"
        description="Set how many competitors each school may register per skill area. The same limit applies to every school."
        backHref={`/admin/competitions/${competitionId}`}
        backLabel="Competition"
      />

      <ApiErrorAlert error={error} title="Could not save school quotas" />

      {savedMessage ? (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{savedMessage}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      ) : null}

      {!loading && quotas.length === 0 ? (
        <Alert>
          <AlertTitle>No skill areas yet</AlertTitle>
          <AlertDescription>
            Add active skills before configuring school quotas.{" "}
            <Link
              className="underline underline-offset-2"
              href={`/admin/competitions/${competitionId}/skills`}
            >
              Go to Skills
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card data-testid="school-quotas-form">
        <CardHeader>
          <CardTitle className="text-base">Per-skill school quotas</CardTitle>
          <CardDescription>
            One max per skill area — applied to all schools in this competition.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={onSave} noValidate>
            <div className="space-y-2">
              <Label>Skill area quotas</Label>
              <FieldMessage id="limits-error" message={fieldErrors.limits} />
              {quotas.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Skill area</TableHead>
                      <TableHead className="w-40">
                        Max per school
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {quotas.map((row) => (
                      <TableRow key={row.skillId}>
                        <TableCell className="font-medium">
                          {row.skillName}
                          {!row.configured ? (
                            <span className="ml-2 text-xs text-muted-foreground">
                              (not set)
                            </span>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <Input
                            className="min-h-10"
                            type="number"
                            min={0}
                            max={1000}
                            step={1}
                            inputMode="numeric"
                            value={maxBySkill[row.skillId] ?? ""}
                            onChange={(e) =>
                              setMaxBySkill((prev) => ({
                                ...prev,
                                [row.skillId]: e.target.value,
                              }))
                            }
                            placeholder="—"
                            data-testid={`max-${row.skillId}`}
                            aria-invalid={Boolean(
                              fieldErrors[`max-${row.skillId}`],
                            )}
                          />
                          <FieldMessage
                            id={`max-${row.skillId}-error`}
                            message={fieldErrors[`max-${row.skillId}`]}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : null}
            </div>

            <Button
              type="submit"
              className="min-h-11"
              disabled={pending || quotas.length === 0}
              data-testid="save-school-quotas"
            >
              {pending ? "Saving…" : "Save quotas"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
