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
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

  const expertRole = useMemo(() => {
    if (!user) return false;
    return user.role === "EXPERT" || user.role === "CHIEF_EXPERT";
  }, [user]);

  const canEditAdmin = me && isSuperAdminRole(me.role);

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
    </PageShell>
  );
}
