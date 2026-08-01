"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  InstitutionListItem,
  UserOut,
  isSuperAdminRole,
  listInstitutions,
  listUsers,
  patchUser,
  resetUserPassword,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  GHANA_PHONE_FORMAT_HINT,
  ghanaPhoneFieldError,
  requiredGhanaPhoneError,
} from "@/lib/phone";

const NO_INSTITUTION = "__none__";

export default function EditUserPage() {
  const params = useParams<{ userId: string }>();
  const userId = params.userId;
  const { me } = useAuth();

  const [user, setUser] = useState<UserOut | null>(null);
  const [institutions, setInstitutions] = useState<InstitutionListItem[]>([]);
  const [fullName, setFullName] = useState("");
  const [institutionId, setInstitutionId] = useState(NO_INSTITUTION);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetPending, setResetPending] = useState(false);
  const [resetError, setResetError] = useState<ApiError | null>(null);
  const [resetFieldErrors, setResetFieldErrors] = useState<
    Record<string, string>
  >({});
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [smsSent, setSmsSent] = useState(false);
  const [smsError, setSmsError] = useState<string | null>(null);
  const [sendViaSms, setSendViaSms] = useState(false);
  const [smsPhone, setSmsPhone] = useState("");
  const [copied, setCopied] = useState(false);

  const expertRole = useMemo(() => {
    if (!user) return false;
    return user.role === "EXPERT" || user.role === "CHIEF_EXPERT";
  }, [user]);

  const canEditAdmin = me && isSuperAdminRole(me.role);

  const canResetPassword = useMemo(() => {
    if (!me || !user) return false;
    if (user.role === "ADMIN" || user.role === "SUPER_ADMIN") {
      return isSuperAdminRole(me.role);
    }
    return true;
  }, [me, user]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [allUsers, inst] = await Promise.all([
          listUsers(),
          listInstitutions(),
        ]);
        if (cancelled) return;
        setInstitutions(inst);
        const found = allUsers.find((u) => u.userId === userId) ?? null;
        setUser(found);
        if (found) {
          setFullName(found.fullName);
          setInstitutionId(found.institutionId ?? NO_INSTITUTION);
          setSmsPhone(found.phoneNumber ?? "");
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setLoadError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError(null);
    setFieldErrors({});
    setSaved(false);
    setPending(true);
    try {
      const payload: {
        fullName?: string;
        institutionId?: string | null;
      } = {
        fullName: fullName.trim(),
      };
      if (expertRole) {
        payload.institutionId =
          institutionId === NO_INSTITUTION ? null : institutionId;
      }
      const updated = await patchUser(userId, payload);
      setUser(updated);
      setInstitutionId(updated.institutionId ?? NO_INSTITUTION);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  async function onConfirmReset() {
    setResetError(null);
    if (sendViaSms) {
      const phoneErr = requiredGhanaPhoneError(smsPhone);
      if (phoneErr) {
        setResetFieldErrors({ phoneNumber: phoneErr });
        return;
      }
    }
    setResetFieldErrors({});
    setResetPending(true);
    setCopied(false);
    try {
      const out = await resetUserPassword(userId, {
        sendViaSms: sendViaSms || undefined,
        phoneNumber: sendViaSms ? smsPhone.trim() || undefined : undefined,
      });
      setTempPassword(out.temporaryPassword);
      setSmsSent(Boolean(out.smsSent));
      setSmsError(out.smsError ?? null);
      setUser((prev) =>
        prev
          ? {
              ...prev,
              mustChangePassword: out.mustChangePassword,
              phoneNumber: out.phoneNumber ?? prev.phoneNumber,
            }
          : prev,
      );
      setResetConfirmOpen(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setResetError(err);
        setResetFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setResetPending(false);
    }
  }

  async function copyTempPassword() {
    if (!tempPassword) return;
    try {
      await navigator.clipboard.writeText(tempPassword);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  if (loading) {
    return (
      <PageShell width="narrow">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="mt-6 h-48 w-full" />
      </PageShell>
    );
  }

  if (loadError) {
    return (
      <PageShell width="narrow">
        <PageHeader
          title="Edit account"
          backHref="/admin/users"
          backLabel="Staff accounts"
        />
        <ApiErrorAlert error={loadError} />
      </PageShell>
    );
  }

  if (!user) {
    return (
      <PageShell width="narrow">
        <PageHeader
          title="Account not found"
          backHref="/admin/users"
          backLabel="Staff accounts"
        />
        <p className="text-sm text-muted-foreground">
          No staff account matches this ID.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title={user.fullName}
        description={user.email}
        backHref="/admin/users"
        backLabel="Staff accounts"
        actions={
          <Badge variant="secondary" className="rounded-full">
            {user.role}
          </Badge>
        }
      />

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardDescription>
            Update display name and institution link for conflict-of-interest
            checks. Role changes are not supported here.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-4 sm:px-6">
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="fullName">Full name</Label>
              <Input
                id="fullName"
                required
                className="min-h-11"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
              <FieldMessage message={fieldErrors.fullName} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                className="min-h-11"
                value={user.email}
                readOnly
                disabled
              />
            </div>
            {expertRole ? (
              <div className="space-y-2">
                <Label htmlFor="institutionId">Institution (COI)</Label>
                <Select value={institutionId} onValueChange={setInstitutionId}>
                  <SelectTrigger id="institutionId" className="min-h-11 w-full">
                    <SelectValue placeholder="Institution" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_INSTITUTION}>None</SelectItem>
                    {institutions.map((i) => (
                      <SelectItem key={i.institutionId} value={i.institutionId}>
                        {i.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Choose None when the expert is not tied to a school for COI
                  purposes.
                </p>
                <FieldMessage message={fieldErrors.institutionId} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Institution is only editable for expert roles.
              </p>
            )}
            {user.role === "ADMIN" && !canEditAdmin ? (
              <p className="text-sm text-muted-foreground">
                Administrator accounts can only be edited by a super
                administrator.
              </p>
            ) : null}
            <ApiErrorAlert error={error} title="Could not save account" />
            <Button type="submit" className="min-h-11 w-full" disabled={pending}>
              {pending ? "Saving…" : "Save changes"}
            </Button>
            <Button variant="link" className="min-h-11 px-0" asChild>
              <Link href="/admin/users">Back to list</Link>
            </Button>
            {saved ? (
              <Alert>
                <AlertTitle>Saved</AlertTitle>
                <AlertDescription>Account updated.</AlertDescription>
              </Alert>
            ) : null}
          </form>
        </CardContent>
      </Card>

      {canResetPassword ? (
        <Card>
          <CardHeader className="px-4 sm:px-6">
            <CardTitle className="text-base">Password</CardTitle>
            <CardDescription>
              Generate an 8-character temporary password and share it securely
              (or send it by SMS). The user must change it on next sign-in.
              Existing sessions are revoked.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 px-4 sm:px-6">
            {tempPassword ? (
              <Alert data-testid="password-reset-result">
                <AlertTitle>Temporary password (shown once)</AlertTitle>
                <AlertDescription className="space-y-3">
                  <p className="font-mono text-sm break-all">{tempPassword}</p>
                  {smsSent ? (
                    <p className="text-sm">SMS sent to the user.</p>
                  ) : null}
                  {smsError ? (
                    <p className="text-sm text-destructive">
                      SMS was not delivered: {smsError}. Share the password out
                      of band instead.
                    </p>
                  ) : null}
                  {!smsSent && !smsError ? (
                    <p className="text-sm">
                      Share this securely. The user must change it after signing
                      in.
                    </p>
                  ) : null}
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11"
                    onClick={copyTempPassword}
                  >
                    {copied ? "Copied" : "Copy password"}
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}
            <ApiErrorAlert error={resetError} title="Could not reset password" />
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full"
              data-testid="reset-password-button"
              onClick={() => {
                setResetError(null);
                setResetFieldErrors({});
                setSendViaSms(false);
                setSmsPhone(user.phoneNumber ?? "");
                setResetConfirmOpen(true);
              }}
            >
              Reset password
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="px-4 sm:px-6">
            <CardTitle className="text-base">Password</CardTitle>
            <CardDescription>
              Only a super administrator can reset passwords for administrator
              accounts.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Dialog open={resetConfirmOpen} onOpenChange={setResetConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset password?</DialogTitle>
            <DialogDescription>
              This replaces {user.fullName}&apos;s password with an 8-character
              temporary one, forces a password change on next login, and signs
              them out of all sessions. Confirm the person&apos;s identity before
              sharing the new password.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <label className="flex items-start gap-3 text-sm">
              <Checkbox
                checked={sendViaSms}
                onCheckedChange={(v) => setSendViaSms(v === true)}
                data-testid="send-via-sms"
                className="mt-0.5"
              />
              <span>Send temporary password by SMS</span>
            </label>
            {sendViaSms ? (
              <div className="space-y-2">
                <Label htmlFor="smsPhone">Phone number</Label>
                <Input
                  id="smsPhone"
                  className="min-h-11"
                  placeholder="e.g. 0551234567"
                  value={smsPhone}
                  onChange={(e) => {
                    const next = e.target.value;
                    setSmsPhone(next);
                    setResetFieldErrors((prev) => {
                      const phoneErr = ghanaPhoneFieldError(next);
                      if (!phoneErr && !prev.phoneNumber) return prev;
                      const copy = { ...prev };
                      if (phoneErr) copy.phoneNumber = phoneErr;
                      else delete copy.phoneNumber;
                      return copy;
                    });
                  }}
                  onBlur={() => {
                    const phoneErr = ghanaPhoneFieldError(smsPhone);
                    setResetFieldErrors((prev) => {
                      if (!phoneErr && !prev.phoneNumber) return prev;
                      const copy = { ...prev };
                      if (phoneErr) copy.phoneNumber = phoneErr;
                      else delete copy.phoneNumber;
                      return copy;
                    });
                  }}
                  aria-invalid={Boolean(resetFieldErrors.phoneNumber)}
                  data-testid="sms-phone-input"
                />
                <p className="text-xs text-muted-foreground">
                  {user.phoneNumber
                    ? "Prefilled from the account phone. Change only to override."
                    : GHANA_PHONE_FORMAT_HINT}
                </p>
                <FieldMessage message={resetFieldErrors.phoneNumber} />
                <FieldMessage message={resetFieldErrors.sendViaSms} />
              </div>
            ) : null}
            <ApiErrorAlert error={resetError} title="Could not reset password" />
          </div>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={resetPending}
              onClick={() => setResetConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="min-h-11"
              disabled={resetPending}
              data-testid="reset-password-confirm"
              onClick={onConfirmReset}
            >
              {resetPending ? "Resetting…" : "Reset password"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
