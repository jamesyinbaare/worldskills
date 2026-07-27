"use client";

import Link from "next/link";
import { FormEvent, Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, homeForRole, registerAccount } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
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

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-md px-4 py-16 text-sm text-muted-foreground">
          Loading…
        </div>
      }
    >
      <SignupContent />
    </Suspense>
  );
}

function SignupContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useAuth();
  const nextPath = useMemo(
    () => safeNextPath(searchParams.get("next")),
    [searchParams],
  );

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const loginHref = nextPath
    ? `/login?next=${encodeURIComponent(nextPath)}`
    : "/login";
  const institutionSignupHref = nextPath
    ? `/signup/institution?next=${encodeURIComponent(nextPath)}`
    : "/signup/institution";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const me = await registerAccount({
        email: email.trim(),
        fullName: fullName.trim(),
        password,
        passwordConfirm,
        captchaToken: "ok",
      });
      await refresh();
      router.push(
        nextPath ?? homeForRole(me.role, Boolean(me.must_change_password)),
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
          <p className="text-sm text-muted-foreground">
            Skills Competition Management System
          </p>
        </div>

        <Card className="w-full shadow-sm ring-primary/10">
          <CardHeader className="space-y-1.5 px-4 pt-6 sm:px-6">
            <h1 className="text-xl font-bold tracking-tight text-primary sm:text-2xl">
              Create competitor account
            </h1>
            <CardDescription>
              Sign up to register for competitions and submit work.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="fullName">Full name</Label>
                <Input
                  id="fullName"
                  name="fullName"
                  autoComplete="name"
                  required
                  className="min-h-11"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  aria-invalid={Boolean(fieldErrors.fullName)}
                />
                <FieldMessage message={fieldErrors.fullName} />
              </div>
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
                  aria-invalid={Boolean(fieldErrors.email)}
                />
                <FieldMessage message={fieldErrors.email} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  className="min-h-11"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-invalid={Boolean(fieldErrors.password)}
                />
                <FieldMessage message={fieldErrors.password} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="passwordConfirm">Confirm password</Label>
                <Input
                  id="passwordConfirm"
                  name="passwordConfirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  className="min-h-11"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  aria-invalid={Boolean(fieldErrors.passwordConfirm)}
                />
                <FieldMessage message={fieldErrors.passwordConfirm} />
              </div>
              <ApiErrorAlert error={error} title="Sign-up failed" />
              <Button
                type="submit"
                className="min-h-11 w-full"
                disabled={pending}
              >
                {pending ? "Creating account…" : "Create account"}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3 px-4 pb-6 sm:px-6">
            <p className="text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link
                href={loginHref}
                className="font-medium text-primary underline underline-offset-2"
              >
                Sign in
              </Link>
            </p>
            <p className="text-sm text-muted-foreground">
              Registering students for a school?{" "}
              <Link
                href={institutionSignupHref}
                className="font-medium text-primary underline underline-offset-2"
              >
                Claim a school account
              </Link>
            </p>
            <Button variant="link" className="min-h-11 justify-start px-0" asChild>
              <Link href="/">Back to home</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
