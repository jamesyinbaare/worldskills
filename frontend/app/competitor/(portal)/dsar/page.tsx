"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  ApiError,
  createDsar,
  type DsarJobOut,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
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
import { Textarea } from "@/components/ui/textarea";

export default function CompetitorDsarPage() {
  const [subjectId, setSubjectId] = useState("");
  const [dsarType, setDsarType] = useState("ACCESS");
  const [dsarOut, setDsarOut] = useState<DsarJobOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const out = await createDsar({
        subjectId: subjectId.trim(),
        type: dsarType,
      });
      setDsarOut(out);
    } catch (err) {
      setDsarOut(null);
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not submit request",
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
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="My data requests"
        description="Request a copy of your personal data, withdraw public-display consent, or ask for erasure where competition integrity allows."
      />

      <ApiErrorAlert error={error} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Lodge a request</CardTitle>
          <CardDescription>
            Use your competitor ID. Only verified subjects for that record may
            proceed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="subjectId">Competitor ID</Label>
              <Input
                id="subjectId"
                className="min-h-11"
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
                required
                data-testid="dsar-subject-id"
              />
              <FieldMessage message={fieldErrors.subjectId} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dsarType">Request type</Label>
              <select
                id="dsarType"
                className="flex min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm"
                value={dsarType}
                onChange={(e) => setDsarType(e.target.value)}
                data-testid="dsar-type"
              >
                <option value="ACCESS">Access (export)</option>
                <option value="WITHDRAW">Withdraw public consent</option>
                <option value="ERASURE">Erasure</option>
              </select>
            </div>
            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={pending}
              data-testid="dsar-submit"
            >
              {pending ? "Submitting…" : "Submit"}
            </Button>
          </form>
          {dsarOut ? (
            <Alert className="mt-4" data-testid="dsar-result">
              <AlertTitle className="flex items-center gap-2">
                Request <StatusBadge status={dsarOut.status} />
              </AlertTitle>
              <AlertDescription>
                <p className="font-mono text-xs">{dsarOut.jobId}</p>
                {dsarOut.resultSummary ? (
                  <p className="mt-2">{dsarOut.resultSummary}</p>
                ) : null}
                {dsarOut.export ? (
                  <Textarea
                    className="mt-3 font-mono text-xs"
                    readOnly
                    rows={10}
                    value={JSON.stringify(dsarOut.export, null, 2)}
                    data-testid="dsar-export"
                  />
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        <Link href="/competitor" className="underline underline-offset-2">
          Back to competitor portal
        </Link>
      </p>
    </PageShell>
  );
}
