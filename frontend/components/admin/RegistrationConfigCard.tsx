"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  getRegistrationFormAdmin,
  getRegistrationWindow,
  putRegistrationFormAdmin,
  putRegistrationWindow,
  type RegistrationFormAdminOut,
  type RegistrationWindowOut,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function toLocalInput(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInput(local: string): string {
  const d = new Date(local);
  return d.toISOString();
}

export function RegistrationConfigCard({
  competitionId,
  className,
}: {
  competitionId: string;
  className?: string;
}) {
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [formMeta, setFormMeta] = useState<RegistrationFormAdminOut | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [pendingWindow, setPendingWindow] = useState(false);
  const [pendingForm, setPendingForm] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const [window, form] = await Promise.all([
          getRegistrationWindow(competitionId),
          getRegistrationFormAdmin(competitionId),
        ]);
        if (cancelled) return;
        applyWindow(window);
        setFormMeta(form);
        setError(null);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  function applyWindow(window: RegistrationWindowOut | null) {
    if (!window) {
      setOpensAt("");
      setClosesAt("");
      return;
    }
    setOpensAt(toLocalInput(window.opensAt));
    setClosesAt(toLocalInput(window.closesAt));
  }

  async function onSaveWindow(e: FormEvent) {
    e.preventDefault();
    setPendingWindow(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await putRegistrationWindow(competitionId, {
        opensAt: fromLocalInput(opensAt),
        closesAt: fromLocalInput(closesAt),
      });
      applyWindow(saved);
      setMessage("Registration window saved.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPendingWindow(false);
    }
  }

  async function onEnsureForm() {
    setPendingForm(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await putRegistrationFormAdmin(competitionId, {
        useDefaults: true,
      });
      setFormMeta(saved);
      setMessage("Default registration form applied.");
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPendingForm(false);
    }
  }

  return (
    <div
      id="registration"
      className={cn(
        "admin-panel space-y-6 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7",
        className,
      )}
    >
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          Registration
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Open/close window and form definition for public registration.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Loading registration config…
        </p>
      ) : (
        <>
          <form onSubmit={onSaveWindow} className="space-y-4" noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="regOpensAt">Opens at</Label>
                <Input
                  id="regOpensAt"
                  type="datetime-local"
                  className="min-h-11"
                  required
                  value={opensAt}
                  onChange={(e) => setOpensAt(e.target.value)}
                  data-testid="registration-opens-at"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="regClosesAt">Closes at</Label>
                <Input
                  id="regClosesAt"
                  type="datetime-local"
                  className="min-h-11"
                  required
                  value={closesAt}
                  onChange={(e) => setClosesAt(e.target.value)}
                  data-testid="registration-closes-at"
                />
              </div>
            </div>
            <Button
              type="submit"
              className="min-h-11"
              disabled={pendingWindow}
              data-testid="registration-window-save"
            >
              {pendingWindow ? "Saving…" : "Save registration window"}
            </Button>
          </form>

          <div className="space-y-3 border-t border-border pt-4">
            <p className="text-sm text-muted-foreground">
              {formMeta
                ? `Form configured (${formMeta.fields.length} fields, max ${formMeta.maxSkills} skill${formMeta.maxSkills === 1 ? "" : "s"}).`
                : "No registration form yet — apply defaults before registration can open."}
            </p>
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={pendingForm}
              onClick={onEnsureForm}
              data-testid="registration-form-defaults"
            >
              {pendingForm
                ? "Applying…"
                : formMeta
                  ? "Reset form to defaults"
                  : "Apply default registration form"}
            </Button>
          </div>
        </>
      )}
      <ApiErrorAlert error={error} title="Could not update registration" />
      {message ? (
        <p className="text-sm text-muted-foreground" role="status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
