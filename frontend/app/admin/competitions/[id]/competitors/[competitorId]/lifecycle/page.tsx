"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  substituteCompetitor,
  withdrawCompetitor,
  type SubstituteOut,
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
import { Checkbox } from "@/components/ui/checkbox";
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
import { Textarea } from "@/components/ui/textarea";

/** Admin oversight mirror of institution lifecycle flows. */
export default function AdminLifecyclePage() {
  const params = useParams<{ id: string; competitorId: string }>();
  const competitionId = params.id;
  const competitorId = params.competitorId;

  const [withdrawReason, setWithdrawReason] = useState("");
  const [withdrawOut, setWithdrawOut] = useState<WithdrawOut | null>(null);
  const [substituteOut, setSubstituteOut] = useState<SubstituteOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);

  const [refNo, setRefNo] = useState("");
  const [givenNames, setGivenNames] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [nationality, setNationality] = useState("");
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState("");
  const [enrolmentAttested, setEnrolmentAttested] = useState(false);

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

  async function onSubstitute(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    setStatusMessage(null);
    try {
      const out = await substituteCompetitor(competitorId, {
        refNo: refNo.trim(),
        givenNames: givenNames.trim(),
        familyName: familyName.trim(),
        dateOfBirth: dateOfBirth.trim(),
        nationality: nationality.trim() || null,
        enrolmentAttested,
        email: email.trim() || null,
        mobile: mobile.trim() || null,
      });
      setSubstituteOut(out);
      setStatusMessage(
        out.eligible
          ? `Substitution applied. Replacement ${out.replacementCompetitorId}.`
          : "Replacement recorded but eligibility failed.",
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
              message: "Could not substitute competitor",
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
        description="Admin withdraw / substitute oversight for this competition competitor."
      />

      <p className="text-sm text-muted-foreground">
        Competition <span className="font-mono">{competitionId}</span>
        {" · "}
        Competitor <span className="font-mono">{competitorId}</span>
      </p>

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
          <CardDescription>Reason required before confirmation.</CardDescription>
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
                {withdrawOut.promotedCompetitorId
                  ? `Promoted: ${withdrawOut.promotedCompetitorId}`
                  : "No waitlist promotion returned."}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Substitute</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubstitute} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="refNo">Reference number</Label>
              <Input
                id="refNo"
                className="min-h-11"
                value={refNo}
                onChange={(e) => setRefNo(e.target.value)}
                required
                data-testid="lifecycle-sub-ref"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="givenNames">Given names</Label>
                <Input
                  id="givenNames"
                  className="min-h-11"
                  value={givenNames}
                  onChange={(e) => setGivenNames(e.target.value)}
                  required
                  data-testid="lifecycle-sub-given"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="familyName">Family name</Label>
                <Input
                  id="familyName"
                  className="min-h-11"
                  value={familyName}
                  onChange={(e) => setFamilyName(e.target.value)}
                  required
                  data-testid="lifecycle-sub-family"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="dateOfBirth">Date of birth</Label>
              <Input
                id="dateOfBirth"
                type="date"
                className="min-h-11"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                required
                data-testid="lifecycle-sub-dob"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nationality">Nationality (optional)</Label>
              <Input
                id="nationality"
                className="min-h-11"
                value={nationality}
                onChange={(e) => setNationality(e.target.value)}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">Email (optional)</Label>
                <Input
                  id="email"
                  type="email"
                  className="min-h-11"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mobile">Mobile (optional)</Label>
                <Input
                  id="mobile"
                  className="min-h-11"
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                />
              </div>
            </div>
            <label className="flex min-h-11 items-center gap-3 text-sm">
              <Checkbox
                checked={enrolmentAttested}
                onCheckedChange={(v) => setEnrolmentAttested(Boolean(v))}
              />
              Enrolment attested
            </label>
            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={pending}
              data-testid="lifecycle-substitute"
            >
              {pending ? "Submitting…" : "Submit substitution"}
            </Button>
          </form>
          {substituteOut ? (
            <Alert className="mt-4" data-testid="lifecycle-substitute-result">
              <AlertTitle className="flex items-center gap-2">
                Substitution <StatusBadge status={substituteOut.status} />
              </AlertTitle>
              <AlertDescription>
                Replacement {substituteOut.replacementCompetitorId}
                {substituteOut.failedRules.length > 0 ? (
                  <ul className="mt-2 list-disc pl-5">
                    {substituteOut.failedRules.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                ) : null}
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
              Reason: {withdrawReason}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => setConfirmWithdraw(false)}
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
              Confirm withdraw
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="text-xs text-muted-foreground">
        <Link
          href={`/admin/competitions/${competitionId}`}
          className="underline underline-offset-2"
        >
          Back to cycle workspace
        </Link>
      </p>
    </PageShell>
  );
}
