"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  listInstitutionRegistrations,
  withdrawCompetitor,
  type InstitutionRegistrationOut,
  type WithdrawOut,
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function LifecyclePage() {
  const params = useParams<{ competitorId: string }>();
  const competitorId = params.competitorId;

  const [withdrawReason, setWithdrawReason] = useState("");
  const [withdrawOut, setWithdrawOut] = useState<WithdrawOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [summary, setSummary] = useState<InstitutionRegistrationOut | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listInstitutionRegistrations();
        if (cancelled) return;
        setSummary(
          rows.find((row) => row.competitorId === competitorId) ?? null,
        );
      } catch {
        if (!cancelled) setSummary(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitorId]);

  const competitorName = useMemo(() => {
    if (!summary) return null;
    return [summary.givenNames, summary.familyName].filter(Boolean).join(" ");
  }, [summary]);

  async function doWithdraw() {
    if (!withdrawReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      setConfirmWithdraw(false);
      return;
    }
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await withdrawCompetitor(competitorId, withdrawReason.trim());
      setWithdrawOut(out);
      setConfirmWithdraw(false);
      setStatusMessage(
        out.promotedCompetitorId
          ? `Withdrawn. Waitlist competitor ${out.promotedCompetitorId} was promoted.`
          : `Competitor withdrawn (${out.status}).`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not withdraw competitor",
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
        title="Competitor lifecycle"
        description="Withdraw a competitor with a required reason. Waitlist promotion may follow when available."
        backHref={
          summary
            ? `/institution/competitions/${summary.competitionId}`
            : "/institution"
        }
      />

      <Card>
        <CardContent className="space-y-3 py-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-lg font-semibold">
                {competitorName || "Competitor details"}
              </p>
              {summary ? (
                <p className="text-sm text-muted-foreground">
                  {summary.competitionName} · {summary.skillName}
                  {summary.gender ? ` · ${summary.gender}` : ""}
                </p>
              ) : null}
            </div>
            {summary ? <StatusBadge status={summary.status} /> : null}
          </div>

          <div className="space-y-1 text-sm text-muted-foreground">
            <p>
              Ref:{" "}
              <span
                className="font-mono text-xs"
                data-testid="lifecycle-competitor-ref"
              >
                {summary?.competitorRef ?? competitorId}
              </span>
            </p>
            <p>
              Competitor ID{" "}
              <span className="font-mono" data-testid="lifecycle-competitor-id">
                {competitorId}
              </span>
            </p>
          </div>

          {summary ? (
            <Button variant="outline" className="min-h-11" asChild>
              <Link href={`/institution/competitions/${summary.competitionId}`}>
                View competition
              </Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {statusMessage ? (
        <Alert data-testid="lifecycle-status-message">
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}

      <ApiErrorAlert error={error} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Withdraw</CardTitle>
          <CardDescription>
            A reason is required. Waitlist promotion may follow when the API
            returns a promoted competitor.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="withdrawReason">Reason (required)</Label>
            <Textarea
              id="withdrawReason"
              value={withdrawReason}
              onChange={(e) => setWithdrawReason(e.target.value)}
              required
              rows={3}
              data-testid="lifecycle-withdraw-reason"
              aria-invalid={Boolean(fieldErrors.reason)}
            />
            <FieldMessage message={fieldErrors.reason} />
          </div>
          <Button
            type="button"
            variant="destructive"
            className="min-h-11 w-full"
            disabled={pending}
            onClick={() => {
              if (!withdrawReason.trim()) {
                setFieldErrors({ reason: "REASON_REQUIRED" });
                return;
              }
              setFieldErrors({});
              setConfirmWithdraw(true);
            }}
            data-testid="lifecycle-withdraw-open"
          >
            Withdraw competitor
          </Button>
          {withdrawOut ? (
            <Alert data-testid="lifecycle-withdraw-result">
              <AlertTitle className="flex items-center gap-2">
                Withdrawn <StatusBadge status={withdrawOut.status} />
              </AlertTitle>
              <AlertDescription>
                {withdrawOut.promotedCompetitorId ? (
                  <p data-testid="lifecycle-promoted">
                    Promoted from waitlist:{" "}
                    <span className="font-mono text-xs">
                      {withdrawOut.promotedCompetitorId}
                    </span>
                  </p>
                ) : (
                  <p>No waitlist promotion returned.</p>
                )}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={confirmWithdraw} onOpenChange={setConfirmWithdraw}>
        <DialogContent data-testid="lifecycle-withdraw-confirm">
          <DialogHeader>
            <DialogTitle>Confirm withdrawal</DialogTitle>
            <DialogDescription>
              This withdraws the competitor and may promote from the waitlist.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Reason: {withdrawReason}
          </p>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => setConfirmWithdraw(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              className="min-h-11"
              disabled={pending}
              onClick={() => void doWithdraw()}
              data-testid="lifecycle-withdraw-confirm-submit"
            >
              {pending ? "Withdrawing…" : "Confirm withdraw"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
