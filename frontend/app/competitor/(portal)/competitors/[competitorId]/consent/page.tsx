"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  downloadConsentForm,
  downloadUploadedConsentForm,
  fetchUploadedConsentForm,
  listMyRegistrations,
  triggerBrowserDownload,
  uploadSignedConsentForm,
  withdrawConsent,
  type ConsentFormUploadOut,
  type ConsentWithdrawOut,
  type MyRegistrationOut,
} from "@/lib/api";
import {
  ApiErrorAlert,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
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

export default function CompetitorConsentPage() {
  const params = useParams<{ competitorId: string }>();
  const competitorId = params.competitorId;

  const [registration, setRegistration] = useState<MyRegistrationOut | null>(
    null,
  );
  const [file, setFile] = useState<File | null>(null);
  const [participation, setParticipation] = useState(true);
  const [publicDisplay, setPublicDisplay] = useState(false);
  const [grantedBy, setGrantedBy] = useState("");

  const [uploadOut, setUploadOut] = useState<ConsentFormUploadOut | null>(null);
  const [withdrawOut, setWithdrawOut] = useState<ConsentWithdrawOut | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [signedBusy, setSignedBusy] = useState<"view" | "download" | null>(
    null,
  );
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [withdrawConfirm, setWithdrawConfirm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        setRegistration(
          rows.find((row) => row.competitorId === competitorId) ?? null,
        );
      } catch {
        if (!cancelled) setRegistration(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitorId]);

  useEffect(() => {
    return () => {
      if (viewerUrl) URL.revokeObjectURL(viewerUrl);
    };
  }, [viewerUrl]);

  const participationGranted =
    Boolean(registration?.consentParticipationAt) ||
    Boolean(uploadOut?.scopesGranted.includes("participation"));
  const publicGranted =
    Boolean(registration?.consentPublicAt) ||
    Boolean(registration?.publicProfileVisible) ||
    Boolean(uploadOut?.scopesGranted.includes("public")) ||
    Boolean(uploadOut?.publicProfileVisible);
  const formOnFile =
    Boolean(registration?.consentFormUploadedAt) || Boolean(uploadOut);

  function closeViewer() {
    setViewerOpen(false);
    setViewerUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }

  async function onDownload() {
    setError(null);
    setDownloading(true);
    try {
      const { blob, filename } = await downloadConsentForm(competitorId);
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not download consent form",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setDownloading(false);
    }
  }

  async function onViewSigned() {
    setError(null);
    setSignedBusy("view");
    try {
      const { blob } = await fetchUploadedConsentForm(competitorId);
      const url = URL.createObjectURL(
        blob.type ? blob : new Blob([blob], { type: "application/pdf" }),
      );
      setViewerUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setViewerOpen(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not open signed consent form",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setSignedBusy(null);
    }
  }

  async function onDownloadSigned() {
    setError(null);
    setSignedBusy("download");
    try {
      const { blob, filename } = await downloadUploadedConsentForm(competitorId);
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not download signed consent form",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setSignedBusy(null);
    }
  }

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file) {
      setError(
        new ApiError(0, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Choose the signed PDF to upload",
            fields: [{ name: "file", reason: "REQUIRED" }],
            traceId: "",
          },
        }),
      );
      return;
    }
    if (!participation) {
      setError(
        new ApiError(0, {
          error: {
            code: "CONSENT_SCOPE_MISSING",
            message: "Participation consent is required",
            fields: [{ name: "scopes", reason: "CONSENT_SCOPE_MISSING" }],
            traceId: "",
          },
        }),
      );
      return;
    }

    const scopes = ["participation"];
    if (publicDisplay) scopes.push("public");

    setPending(true);
    try {
      const out = await uploadSignedConsentForm(
        competitorId,
        file,
        scopes,
        grantedBy.trim() || null,
      );
      setUploadOut(out);
      setWithdrawOut(null);
      setRegistration((prev) =>
        prev
          ? {
              ...prev,
              consentParticipationAt:
                out.scopesGranted.includes("participation")
                  ? out.consentFormUploadedAt
                  : prev.consentParticipationAt,
              consentPublicAt: out.scopesGranted.includes("public")
                ? out.consentFormUploadedAt
                : prev.consentPublicAt,
              publicProfileVisible: out.publicProfileVisible,
              consentFormUploadedAt: out.consentFormUploadedAt,
              status: out.status,
            }
          : prev,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        fieldErrorMap(err.fields);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not upload signed consent form",
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

  async function onWithdraw() {
    if (!withdrawConfirm) {
      setWithdrawConfirm(true);
      return;
    }
    setError(null);
    setPending(true);
    try {
      const out = await withdrawConsent(competitorId);
      setWithdrawOut(out);
      setUploadOut(null);
      setWithdrawConfirm(false);
      setRegistration((prev) =>
        prev
          ? {
              ...prev,
              consentParticipationAt: null,
              consentPublicAt: null,
              publicProfileVisible: false,
              consentFormUploadedAt: null,
              status: out.status,
            }
          : prev,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not withdraw consent",
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
    <div className="mx-auto max-w-xl space-y-6 px-4 py-8 sm:px-6 sm:py-10">
      <Button variant="link" className="h-auto min-h-11 px-0" asChild>
        <Link href="/competitor">← Competitor portal</Link>
      </Button>

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            Guardian consent
          </h1>
          <CardDescription>
            Download the consent form for your guardian to sign, then upload the
            signed PDF
            {registration ? ` for ${registration.competitionName}` : ""}.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6 px-4 sm:px-6">
          {!participationGranted ? (
            <Alert data-testid="consent-pending-alert" role="status">
              <AlertTitle>Consent recommended</AlertTitle>
              <AlertDescription>
                A signed guardian consent form can be uploaded here. Progression
                is not blocked while consent is pending. Public display stays
                withheld by default.
              </AlertDescription>
            </Alert>
          ) : null}

          <div
            className="flex flex-wrap gap-2"
            data-testid="consent-scope-status"
          >
            <Badge
              variant={participationGranted ? "default" : "outline"}
              data-testid="scope-participation"
              data-granted={participationGranted ? "true" : "false"}
            >
              Participation:{" "}
              {participationGranted ? "granted" : "not granted"}
            </Badge>
            <Badge
              variant={publicGranted ? "default" : "outline"}
              data-testid="scope-public"
              data-granted={publicGranted ? "true" : "false"}
            >
              Public display: {publicGranted ? "granted" : "withheld"}
            </Badge>
          </div>

          <section className="space-y-3" data-testid="consent-download-section">
            <h2 className="text-lg font-medium">1. Download form</h2>
            <p className="text-sm text-muted-foreground">
              Print or share the PDF with your guardian. They must sign it and
              tick the consent scopes.
            </p>
            <Button
              type="button"
              className="min-h-11 w-full"
              disabled={downloading || pending}
              onClick={() => void onDownload()}
              data-testid="consent-download"
            >
              {downloading ? "Preparing PDF…" : "Download consent form"}
            </Button>
          </section>

          <form
            onSubmit={onUpload}
            className="space-y-4 border-t border-border pt-4"
            noValidate
            data-testid="consent-upload-form"
          >
            <h2 className="text-lg font-medium">2. Upload signed PDF</h2>
            <div className="space-y-2">
              <Label htmlFor="consentFile">Signed PDF</Label>
              <Input
                id="consentFile"
                type="file"
                accept="application/pdf,.pdf"
                className="min-h-11"
                disabled={pending}
                data-testid="consent-upload-file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>

            <div className="space-y-3">
              <label className="flex min-h-11 items-center gap-3 text-sm">
                <Checkbox
                  checked={participation}
                  onCheckedChange={(v) => setParticipation(Boolean(v))}
                  data-testid="consent-scope-participation"
                />
                Participation consent (required)
              </label>
              <label className="flex min-h-11 items-center gap-3 text-sm">
                <Checkbox
                  checked={publicDisplay}
                  onCheckedChange={(v) => setPublicDisplay(Boolean(v))}
                  data-testid="consent-scope-public"
                />
                Public display consent (optional)
              </label>
            </div>

            <div className="space-y-2">
              <Label htmlFor="grantedBy">Guardian name on the form (optional)</Label>
              <Input
                id="grantedBy"
                className="min-h-11"
                value={grantedBy}
                disabled={pending}
                data-testid="consent-granted-by"
                onChange={(e) => setGrantedBy(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={pending}
              data-testid="consent-upload-submit"
            >
              {pending ? "Uploading…" : "Upload signed consent"}
            </Button>
          </form>

          {formOnFile || uploadOut ? (
            <div className="space-y-3" data-testid="consent-signed-section">
              <Alert data-testid="consent-upload-result" role="status">
                <AlertTitle>
                  {uploadOut ? "Consent form uploaded" : "Signed consent on file"}
                </AlertTitle>
                <AlertDescription>
                  Status: {uploadOut?.status ?? registration?.status ?? "—"}.
                  {participationGranted ? " Participation granted." : ""}
                  {publicGranted
                    ? " Public display granted."
                    : " Public display withheld."}
                  {registration?.consentFormUploadedAt
                    ? ` Uploaded ${new Date(registration.consentFormUploadedAt).toLocaleString()}.`
                    : ""}
                </AlertDescription>
              </Alert>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 flex-1"
                  disabled={signedBusy !== null || pending}
                  onClick={() => void onViewSigned()}
                  data-testid="consent-view-signed"
                >
                  {signedBusy === "view" ? "Loading…" : "View signed PDF"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 flex-1"
                  disabled={signedBusy !== null || pending}
                  onClick={() => void onDownloadSigned()}
                  data-testid="consent-download-signed"
                >
                  {signedBusy === "download"
                    ? "Downloading…"
                    : "Download signed PDF"}
                </Button>
              </div>
            </div>
          ) : null}

          <div className="space-y-3 border-t border-border pt-4">
            <h2 className="text-lg font-medium">Withdraw consent</h2>
            <p className="text-sm text-muted-foreground">
              Withdrawal removes public display immediately and flags the
              record.
            </p>
            {withdrawConfirm ? (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Confirm withdrawal</AlertTitle>
                <AlertDescription>
                  This withdraws participation and public-display consent.
                </AlertDescription>
              </Alert>
            ) : null}
            <Button
              type="button"
              variant={withdrawConfirm ? "destructive" : "outline"}
              className="min-h-11 w-full"
              disabled={pending}
              onClick={() => void onWithdraw()}
              data-testid="consent-withdraw"
            >
              {withdrawConfirm
                ? "Confirm withdraw consent"
                : "Withdraw consent"}
            </Button>
            {withdrawConfirm ? (
              <Button
                type="button"
                variant="ghost"
                className="min-h-11 w-full"
                onClick={() => setWithdrawConfirm(false)}
              >
                Cancel
              </Button>
            ) : null}
          </div>

          {withdrawOut ? (
            <Alert data-testid="consent-withdraw-result" role="status">
              <AlertTitle>Consent withdrawn</AlertTitle>
              <AlertDescription>
                Status: {withdrawOut.status}. Public display is removed
                {withdrawOut.publicProfileVisible ? "" : " (not visible)"}.
                {withdrawOut.flags.length > 0
                  ? ` Flags: ${withdrawOut.flags.join(", ")}.`
                  : ""}
              </AlertDescription>
            </Alert>
          ) : null}

          <ApiErrorAlert error={error} title="Consent action failed" />
        </CardContent>
      </Card>

      <Dialog
        open={viewerOpen}
        onOpenChange={(open) => {
          if (!open) closeViewer();
          else setViewerOpen(true);
        }}
      >
        <DialogContent
          className="flex max-h-[90vh] w-full flex-col gap-3 sm:max-w-4xl"
          data-testid="consent-signed-viewer"
          showCloseButton
        >
          <DialogHeader>
            <DialogTitle>Signed consent form</DialogTitle>
            <DialogDescription>
              Preview of the uploaded guardian consent PDF.
            </DialogDescription>
          </DialogHeader>
          {viewerUrl ? (
            <iframe
              title="Signed consent form PDF"
              src={viewerUrl}
              className="h-[min(70vh,720px)] w-full rounded-lg border border-border bg-muted"
            />
          ) : null}
          <DialogFooter className="gap-2 sm:justify-between">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={signedBusy !== null}
              onClick={() => void onDownloadSigned()}
            >
              {signedBusy === "download" ? "Downloading…" : "Download"}
            </Button>
            <Button
              type="button"
              className="min-h-11"
              onClick={closeViewer}
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
