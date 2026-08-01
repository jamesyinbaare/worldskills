"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ApiError, forgotPassword } from "@/lib/api";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isValidGhanaPhone } from "@/lib/phone";

function looksLikeEmail(value: string): boolean {
  return value.includes("@");
}

function isPhoneShaped(value: string): boolean {
  return /^[+()\d\s-]+$/.test(value);
}

/** Plausible email local-part while typing (before @). Not digit-heavy junk. */
function isEmailLocalPartInProgress(value: string): boolean {
  if (!/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(value)) return false;
  const digits = value.replace(/\D/g, "");
  // Digits approaching phone length → mangled number, not an email in progress
  return digits.length < 7;
}

const IDENTIFIER_FORMAT_ERROR =
  "Enter a valid email or Ghana mobile number (e.g. 0551234567).";

/** Immediate field error while typing; empty input has no error yet. */
function identifierFieldError(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;

  if (looksLikeEmail(trimmed)) {
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) return undefined;
    // Still typing domain (e.g. "user@g") — wait until a dot appears after @
    const afterAt = trimmed.split("@")[1] ?? "";
    if (!afterAt.includes(".")) return undefined;
    return "Enter a valid email address.";
  }

  if (isPhoneShaped(trimmed)) {
    const digits = trimmed.replace(/\D/g, "");
    if (!digits) return IDENTIFIER_FORMAT_ERROR;
    if (isValidGhanaPhone(trimmed)) return undefined;
    // Allow incomplete numbers without nagging until length looks finished
    if (digits.startsWith("233") && digits.length < 12) return undefined;
    if (digits.startsWith("0") && digits.length < 10) return undefined;
    if (!digits.startsWith("0") && !digits.startsWith("233") && digits.length < 9) {
      return undefined;
    }
    return IDENTIFIER_FORMAT_ERROR;
  }

  // Letters/symbols without @: allow short email local-parts while typing
  if (isEmailLocalPartInProgress(trimmed)) return undefined;

  return IDENTIFIER_FORMAT_ERROR;
}

function resolveIdentifier(
  raw: string,
): { email: string } | { phoneNumber: string } | { error: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { error: "Enter your email or phone number." };
  }
  if (looksLikeEmail(trimmed)) {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      return { error: "Enter a valid email address." };
    }
    return { email: trimmed };
  }
  if (!isValidGhanaPhone(trimmed)) {
    return {
      error: "Enter a valid email or Ghana mobile number (e.g. 0551234567).",
    };
  }
  return { phoneNumber: trimmed };
}

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);

  function updateIdentifier(next: string) {
    setIdentifier(next);
    setFieldError(identifierFieldError(next) ?? null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setDoneMessage(null);

    const resolved = resolveIdentifier(identifier);
    if ("error" in resolved) {
      setFieldError(resolved.error);
      return;
    }
    setFieldError(null);
    setPending(true);
    try {
      const out = await forgotPassword({
        ...resolved,
        captchaToken: "ok",
      });
      setDoneMessage(out.message);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        const mapped = fieldErrorMap(err.fields);
        setFieldError(
          mapped.email || mapped.phoneNumber || mapped.identifier || null,
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="bg-brand-atmosphere">
      <div className="mx-auto flex min-h-[calc(100dvh-4.75rem)] max-w-md flex-col justify-center px-4 py-10 sm:px-6 sm:py-16">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="flex items-center gap-3">
            <CrestLogo className="h-12 w-auto object-contain" />
            <WorldSkillsLogo className="h-10 w-auto max-w-[10rem] object-contain" />
          </div>
        </div>

        <Card className="w-full shadow-sm ring-primary/10">
          <CardHeader className="space-y-1.5 px-4 pt-6 sm:px-6">
            <h1 className="text-xl font-bold tracking-tight text-primary sm:text-2xl">
              Reset password
            </h1>
            <CardDescription>
              Enter your email or phone to receive a temporary password by SMS.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            {doneMessage ? (
              <Alert data-testid="forgot-password-success">
                <AlertTitle>Request sent</AlertTitle>
                <AlertDescription className="space-y-3">
                  <p>{doneMessage}</p>
                  <Button variant="outline" className="min-h-11" asChild>
                    <Link href="/login">Back to sign in</Link>
                  </Button>
                </AlertDescription>
              </Alert>
            ) : (
              <form onSubmit={onSubmit} className="space-y-4" noValidate>
                <div className="space-y-2">
                  <Label htmlFor="identifier">Email/phone</Label>
                  <Input
                    id="identifier"
                    name="identifier"
                    type="text"
                    inputMode="email"
                    autoComplete="username"
                    required
                    className="min-h-11"
                    placeholder="Email or phone number"
                    value={identifier}
                    onChange={(e) => updateIdentifier(e.target.value)}
                    onBlur={() => {
                      const resolved = resolveIdentifier(identifier);
                      if ("error" in resolved) {
                        setFieldError(resolved.error);
                      }
                    }}
                    aria-invalid={Boolean(fieldError)}
                    data-testid="forgot-password-identifier"
                  />
                  <FieldMessage message={fieldError} />
                </div>

                <ApiErrorAlert error={error} title="Could not request reset" />
                <Button
                  type="submit"
                  className="min-h-11 w-full"
                  disabled={pending || Boolean(fieldError)}
                  data-testid="forgot-password-submit"
                >
                  {pending ? "Sending…" : "Send temporary password"}
                </Button>
              </form>
            )}
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3 px-4 pb-6 sm:px-6">
            <p className="text-sm text-muted-foreground">
              Remembered it?{" "}
              <Link
                href="/login"
                className="font-medium text-primary underline underline-offset-2"
              >
                Sign in
              </Link>
            </p>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
