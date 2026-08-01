"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, getPublicSettings, login, resolvePostAuthPath } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
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

function safeNextPath(raw: string | null): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return null;
  return raw;
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-md px-4 py-16 text-sm text-muted-foreground">
          Loading…
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useAuth();
  const nextPath = useMemo(
    () => safeNextPath(searchParams.get("next")),
    [searchParams],
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [institutionSignupEnabled, setInstitutionSignupEnabled] = useState(false);

  const signupHref = nextPath
    ? `/signup?next=${encodeURIComponent(nextPath)}`
    : "/signup";
  const institutionSignupHref = nextPath
    ? `/signup/institution?next=${encodeURIComponent(nextPath)}`
    : "/signup/institution";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const settings = await getPublicSettings();
        if (!cancelled) {
          setInstitutionSignupEnabled(settings.institutionRegistrationEnabled);
        }
      } catch {
        if (!cancelled) setInstitutionSignupEnabled(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const me = await login(email.trim(), password);
      await refresh();
      router.push(
        await resolvePostAuthPath(me.role, {
          nextPath,
          mustChangePassword: Boolean(me.must_change_password),
        }),
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Something went wrong. Please try again.",
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
              Sign in
            </h1>
            <CardDescription>
              Enter the competition portal with your SCMS account.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="username"
                  required
                  className="min-h-11"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!error}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  className="min-h-11"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <ApiErrorAlert error={error} title="Sign-in failed" />
              <Button
                type="submit"
                className="min-h-11 w-full"
                disabled={pending}
              >
                {pending ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3 px-4 pb-6 sm:px-6">
            <p className="text-sm text-muted-foreground">
              New competitor?{" "}
              <Link
                href={signupHref}
                className="font-medium text-primary underline underline-offset-2"
              >
                Create an account
              </Link>
            </p>
            {institutionSignupEnabled ? (
              <p className="text-sm text-muted-foreground">
                School primary contact?{" "}
                <Link
                  href={institutionSignupHref}
                  className="font-medium text-primary underline underline-offset-2"
                >
                  Claim a school account
                </Link>
              </p>
            ) : null}
            <Button variant="link" className="min-h-11 justify-start px-0" asChild>
              <Link href="/">Back to home</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
