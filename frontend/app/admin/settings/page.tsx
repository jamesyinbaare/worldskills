"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getAdminSettings,
  updateAdminSettings,
  type SystemSettingsOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
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
import { Label } from "@/components/ui/label";

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<SystemSettingsOut | null>(null);
  const [draft, setDraft] = useState<SystemSettingsOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const out = await getAdminSettings();
        if (!cancelled) {
          setSettings(out);
          setDraft(out);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err
              : new ApiError(0, {
                  error: {
                    code: "HTTP_ERROR",
                    message: "Could not load settings",
                    fields: [],
                    traceId: "",
                  },
                }),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const dirty =
    draft != null &&
    settings != null &&
    (draft.institutionRegistrationEnabled !==
      settings.institutionRegistrationEnabled ||
      draft.allowMultipleActiveCompetitions !==
        settings.allowMultipleActiveCompetitions);

  async function onSave() {
    if (!draft) return;
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const out = await updateAdminSettings({
        institutionRegistrationEnabled: draft.institutionRegistrationEnabled,
        allowMultipleActiveCompetitions: draft.allowMultipleActiveCompetitions,
      });
      setSettings(out);
      setDraft(out);
      setMessage("Settings saved.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not save settings",
                fields: [],
                traceId: "",
              },
            }),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="System settings"
        description="Platform-wide toggles for registration and competition activation."
      />

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading settings…
        </p>
      ) : null}

      <ApiErrorAlert error={error} title="Settings" />

      {message ? (
        <Alert className="mb-6">
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ) : null}

      {draft ? (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Platform controls</CardTitle>
            <CardDescription>
              Changes apply immediately to public registration and activation
              rules.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-4">
              <input
                type="checkbox"
                className="mt-1 size-4 accent-brand-blue"
                checked={draft.institutionRegistrationEnabled}
                disabled={pending}
                data-testid="setting-institution-registration"
                onChange={(e) =>
                  setDraft((prev) =>
                    prev
                      ? {
                          ...prev,
                          institutionRegistrationEnabled: e.target.checked,
                        }
                      : prev,
                  )
                }
              />
              <span className="space-y-1">
                <Label className="cursor-pointer text-base font-medium">
                  Allow institution registration
                </Label>
                <p className="text-sm text-muted-foreground">
                  When off, schools cannot claim accounts or register
                  competitors on behalf of students.
                </p>
              </span>
            </label>

            <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-4">
              <input
                type="checkbox"
                className="mt-1 size-4 accent-brand-blue"
                checked={draft.allowMultipleActiveCompetitions}
                disabled={pending}
                data-testid="setting-multiple-active"
                onChange={(e) =>
                  setDraft((prev) =>
                    prev
                      ? {
                          ...prev,
                          allowMultipleActiveCompetitions: e.target.checked,
                        }
                      : prev,
                  )
                }
              />
              <span className="space-y-1">
                <Label className="cursor-pointer text-base font-medium">
                  Allow multiple active competitions
                </Label>
                <p className="text-sm text-muted-foreground">
                  When off, only one competition may be ACTIVE. Activating
                  another is blocked until the current one is closed. The public
                  site then shows skill areas of the open competition instead of
                  a competition list.
                </p>
              </span>
            </label>

            <Button
              type="button"
              className="min-h-11"
              disabled={!dirty || pending}
              onClick={() => void onSave()}
              data-testid="settings-save"
            >
              {pending ? "Saving…" : "Save settings"}
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </PageShell>
  );
}
