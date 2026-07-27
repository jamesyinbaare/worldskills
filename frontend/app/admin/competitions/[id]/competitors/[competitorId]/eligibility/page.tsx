"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  overrideEligibility,
  screenCompetitor,
  type EligibilityOverrideOut,
  type EligibilityScreenOut,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ScreenState = EligibilityScreenOut | null;

function humanRule(code: string): string {
  if (code === "AGE_EXCEEDS_LIMIT") {
    return "Age exceeds the skill limit at the configured reference date";
  }
  if (code.startsWith("ELIGIBILITY_FAILED:")) {
    return `Eligibility rule failed (${code.slice("ELIGIBILITY_FAILED:".length)})`;
  }
  return code;
}

export default function EligibilityScreenPage() {
  const params = useParams<{ id: string; competitorId: string }>();
  const competitionId = params.id;
  const competitorId = params.competitorId;

  const [screen, setScreen] = useState<ScreenState>(null);
  const [overrideResult, setOverrideResult] =
    useState<EligibilityOverrideOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [overrideOpen, setOverrideOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [overrideValue, setOverrideValue] = useState(true);
  const [reason, setReason] = useState("");

  const configIncomplete = error?.code === "CONFIG_INCOMPLETE";
  const displayEligible =
    overrideResult?.eligible ?? screen?.eligible ?? null;
  const displayStatus =
    overrideResult?.status ?? screen?.status ?? null;
  const displayCategory =
    overrideResult?.category ?? screen?.category ?? null;
  const failedRules = screen?.failedRules ?? [];

  async function onScreen() {
    setError(null);
    setFieldErrors({});
    setStatusMessage(null);
    setOverrideResult(null);
    setPending(true);
    try {
      const out = await screenCompetitor(competitorId);
      setScreen(out);
      setStatusMessage(
        out.eligible
          ? "Screening complete — competitor may progress."
          : "Screening complete — competitor is ineligible.",
      );
    } catch (err) {
      setScreen(null);
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not screen competitor",
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

  function openOverride() {
    setError(null);
    setFieldErrors({});
    setReason("");
    setOverrideValue(true);
    setOverrideOpen(true);
    setConfirmOpen(false);
  }

  function onOverrideFormSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      setError(
        new ApiError(422, {
          error: {
            code: "REASON_REQUIRED",
            message: "An override reason is required.",
            fields: [{ name: "reason", reason: "REASON_REQUIRED" }],
            traceId: "",
          },
        }),
      );
      return;
    }
    setError(null);
    setFieldErrors({});
    setOverrideOpen(false);
    setConfirmOpen(true);
  }

  async function onConfirmOverride() {
    const trimmed = reason.trim();
    if (!trimmed) {
      setConfirmOpen(false);
      setOverrideOpen(true);
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await overrideEligibility(competitorId, {
        value: overrideValue,
        reason: trimmed,
        category: overrideValue ? "COMPETITIVE" : null,
      });
      setOverrideResult(out);
      setConfirmOpen(false);
      setStatusMessage(
        out.eligible
          ? "Override applied — competitor marked eligible."
          : "Override applied — competitor marked ineligible.",
      );
    } catch (err) {
      setConfirmOpen(false);
      setOverrideOpen(true);
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not override eligibility",
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
    <PageShell>
      <PageHeader
        title="Eligibility screening"
        description={`Competitor ${competitorId}`}
        backHref={`/admin/competitions/${competitionId}`}
        backLabel="Competition workspace"
      />

      {statusMessage ? (
        <Alert className="mb-6" data-testid="eligibility-status-message">
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert
        error={error}
        title={
          configIncomplete
            ? "Configuration incomplete"
            : "Eligibility action failed"
        }
        className="mb-6"
      />

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Screen</CardTitle>
          <CardDescription>
            Run eligibility against skill age and rule config. Results come
            only from the API — this page does not invent pass/fail.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            type="button"
            className="min-h-11"
            disabled={pending}
            onClick={() => void onScreen()}
            data-testid="eligibility-screen"
          >
            {pending ? "Screening…" : "Run screen"}
          </Button>

          {configIncomplete ? (
            <Alert
              variant="destructive"
              data-testid="eligibility-config-incomplete"
              role="alert"
            >
              <AlertTitle>CONFIG_INCOMPLETE</AlertTitle>
              <AlertDescription>
                Missing age reference or rule configuration. The competitor is
                not marked eligible.
              </AlertDescription>
            </Alert>
          ) : null}

          {displayStatus != null ? (
            <div
              className="space-y-3 rounded-lg border border-border p-4"
              data-testid="eligibility-result"
              aria-live="polite"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span data-testid="eligibility-status-badge">
                  <StatusBadge status={displayStatus} />
                </span>
                <span
                  className="text-sm font-medium"
                  data-testid="eligibility-eligible-label"
                  data-eligible={
                    displayEligible === true
                      ? "true"
                      : displayEligible === false
                        ? "false"
                        : "unknown"
                  }
                >
                  {displayEligible === true
                    ? "Eligible — may progress"
                    : displayEligible === false
                      ? "INELIGIBLE"
                      : "Status unknown"}
                </span>
              </div>
              {displayCategory ? (
                <p className="text-sm text-muted-foreground">
                  Category:{" "}
                  <span data-testid="eligibility-category">
                    {displayCategory}
                  </span>
                  {displayCategory === "OPEN" ||
                  displayStatus === "OPEN_CATEGORY"
                    ? " — demonstration / open placement (not competitive selection)"
                    : null}
                </p>
              ) : null}
              {screen?.ageAtReference != null ? (
                <p className="text-sm text-muted-foreground">
                  Age at reference: {screen.ageAtReference}
                </p>
              ) : null}
              {!displayEligible && failedRules.length > 0 ? (
                <div>
                  <p className="text-sm font-medium">Failing rules</p>
                  <ul
                    className="mt-2 list-disc space-y-1 pl-5 text-sm"
                    data-testid="eligibility-failed-rules"
                  >
                    {failedRules.map((rule) => (
                      <li key={rule} data-testid="eligibility-failed-rule">
                        <code className="text-xs">{rule}</code>
                        <span className="text-muted-foreground">
                          {" "}
                          — {humanRule(rule)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Override</CardTitle>
          <CardDescription>
            Admin override requires a reason and confirmation. Overrides are
            audited by the API.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={pending || configIncomplete}
            onClick={openOverride}
            data-testid="eligibility-override-open"
          >
            Override eligibility
          </Button>
          {overrideResult ? (
            <Alert className="mt-4" data-testid="eligibility-override-result">
              <AlertTitle>Override recorded</AlertTitle>
              <AlertDescription>
                New status: {overrideResult.status}. Reason stored server-side.
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent data-testid="eligibility-override-dialog">
          <DialogHeader>
            <DialogTitle>Override eligibility</DialogTitle>
            <DialogDescription>
              Choose the new eligibility value and provide a required reason.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={onOverrideFormSubmit}
            className="space-y-4"
            noValidate
            data-testid="eligibility-override-form"
          >
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">New value</legend>
              <div className="flex flex-col gap-2 sm:flex-row">
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="overrideValue"
                    checked={overrideValue === true}
                    onChange={() => setOverrideValue(true)}
                    data-testid="override-value-eligible"
                  />
                  Eligible
                </label>
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="overrideValue"
                    checked={overrideValue === false}
                    onChange={() => setOverrideValue(false)}
                    data-testid="override-value-ineligible"
                  />
                  Ineligible
                </label>
              </div>
            </fieldset>
            <div className="space-y-2">
              <Label htmlFor="overrideReason">Reason *</Label>
              <Input
                id="overrideReason"
                className="min-h-11"
                value={reason}
                required
                aria-invalid={Boolean(fieldErrors.reason)}
                aria-describedby={
                  fieldErrors.reason ? "overrideReason-error" : undefined
                }
                onChange={(e) => setReason(e.target.value)}
                data-testid="eligibility-override-reason"
              />
              <FieldMessage
                id="overrideReason-error"
                message={fieldErrors.reason}
              />
            </div>
            <ApiErrorAlert error={error} title="Override failed" />
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOverrideOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                data-testid="eligibility-override-continue"
              >
                Continue
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent data-testid="eligibility-override-confirm">
          <DialogHeader>
            <DialogTitle>Confirm override</DialogTitle>
            <DialogDescription>
              Set competitor to{" "}
              <strong>{overrideValue ? "ELIGIBLE" : "INELIGIBLE"}</strong>?
              This action is audited.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirmOpen(false);
                setOverrideOpen(true);
              }}
            >
              Back
            </Button>
            <Button
              type="button"
              disabled={pending}
              onClick={() => void onConfirmOverride()}
              data-testid="eligibility-override-confirm-submit"
            >
              {pending ? "Saving…" : "Confirm override"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="mt-6 text-xs text-muted-foreground">
        <Link
          href={`/admin/competitors?competitionId=${competitionId}`}
          className="underline underline-offset-2"
        >
          Competitors
        </Link>
      </p>
    </PageShell>
  );
}
