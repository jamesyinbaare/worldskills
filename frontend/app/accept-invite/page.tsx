"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, acceptInvite, login } from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-md px-4 py-16 text-sm text-muted-foreground">
          Loading invitation…
        </div>
      }
    >
      <AcceptInviteContent />
    </Suspense>
  );
}

function AcceptInviteContent() {
  const router = useRouter();
  const params = useSearchParams();
  const tokenFromUrl = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [email, setEmail] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await acceptInvite({
        token: tokenFromUrl,
        password,
        passwordConfirm,
      });
      if (email.trim()) {
        const me = await login(email.trim(), password);
        router.push(me.must_change_password ? "/account/change-password" : "/login");
      } else {
        router.push("/login");
      }
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPending(false);
    }
  }

  if (!tokenFromUrl) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <Card>
          <CardHeader>
            <CardDescription>Missing or invalid invitation link.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="min-h-11">
              <Link href="/login">Go to sign in</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <Card>
        <CardHeader className="space-y-1.5">
          <h1 className="text-xl font-bold tracking-tight">Set your password</h1>
          <CardDescription>
            Complete your SCMS account setup. Optionally sign in immediately after.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="email">Email (optional, for sign-in after)</Label>
              <Input
                id="email"
                type="email"
                className="min-h-11"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">New password</Label>
              <Input
                id="password"
                type="password"
                required
                minLength={10}
                className="min-h-11"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="passwordConfirm">Confirm password</Label>
              <Input
                id="passwordConfirm"
                type="password"
                required
                minLength={10}
                className="min-h-11"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
              />
            </div>
            <ApiErrorAlert error={error} title="Could not accept invitation" />
            <Button type="submit" className="min-h-11 w-full" disabled={pending}>
              {pending ? "Saving…" : "Set password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
