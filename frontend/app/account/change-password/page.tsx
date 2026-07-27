"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, changePassword, homeForRole } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
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

export default function ChangePasswordPage() {
  const router = useRouter();
  const { me, refresh } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await changePassword({
        currentPassword,
        newPassword,
        newPasswordConfirm,
      });
      const updated = await refresh();
      if (updated) {
        router.push(homeForRole(updated.role));
      } else {
        router.push("/login");
      }
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <Card>
        <CardHeader className="space-y-1.5">
          <h1 className="text-xl font-bold tracking-tight">Change password</h1>
          <CardDescription>
            {me?.full_name
              ? `Hi ${me.full_name}, set a new password before continuing.`
              : "Set a new password before continuing."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="currentPassword">Current password</Label>
              <Input
                id="currentPassword"
                type="password"
                required
                className="min-h-11"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="newPassword">New password</Label>
              <Input
                id="newPassword"
                type="password"
                required
                minLength={10}
                className="min-h-11"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="newPasswordConfirm">Confirm new password</Label>
              <Input
                id="newPasswordConfirm"
                type="password"
                required
                minLength={10}
                className="min-h-11"
                value={newPasswordConfirm}
                onChange={(e) => setNewPasswordConfirm(e.target.value)}
              />
            </div>
            <ApiErrorAlert error={error} title="Could not change password" />
            <Button type="submit" className="min-h-11 w-full" disabled={pending}>
              {pending ? "Updating…" : "Update password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
