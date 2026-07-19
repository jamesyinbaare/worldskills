"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, isAdminRole, login } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const me = await login(email.trim(), password);
      if (isAdminRole(me.role)) {
        router.push("/admin/cycles");
      } else {
        router.push("/");
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unable to sign in. Check that the API is running.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="bg-brand-atmosphere">
      <div className="mx-auto flex min-h-[calc(100dvh-4.5rem)] max-w-md flex-col justify-center px-4 py-16 sm:px-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-2xl">Sign in</CardTitle>
            <CardDescription>
              Enter the competition portal with your SCMS account.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <Alert variant="destructive">
                  <AlertTitle>Sign-in failed</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" className="w-full" disabled={pending}>
                {pending ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
          <CardFooter>
            <Button variant="link" className="px-0" asChild>
              <Link href="/">Back to home</Link>
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
