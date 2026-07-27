"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, UserOut, listUsers, patchUser } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ROLE_FILTERS = [
  { value: "ALL", label: "All roles" },
  { value: "ADMIN", label: "Administrator" },
  { value: "CHIEF_EXPERT", label: "Chief expert" },
  { value: "EXPERT", label: "Expert" },
  { value: "MODERATOR", label: "Moderator" },
  { value: "APPEALS_OFFICER", label: "Appeals officer" },
] as const;

const ACTIVE_FILTERS = [
  { value: "ALL", label: "All statuses" },
  { value: "true", label: "Active" },
  { value: "false", label: "Inactive" },
] as const;

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [qDraft, setQDraft] = useState("");
  const [role, setRole] = useState("ALL");
  const [active, setActive] = useState("ALL");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setUsers(
        await listUsers({
          q: q.trim() || undefined,
          role: role === "ALL" ? undefined : role,
          active: active === "ALL" ? undefined : active === "true",
        }),
      );
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setLoading(false);
    }
  }, [q, role, active]);

  useEffect(() => {
    void load();
  }, [load]);

  async function setActiveState(userId: string, isActive: boolean) {
    setPendingId(userId);
    setError(null);
    try {
      await patchUser(userId, { isActive });
      await load();
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setPendingId(null);
    }
  }

  return (
    <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel mb-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Staff accounts"
          description="Create experts, moderators and other provisioned roles. Competitors and schools register separately."
          actions={
            <Button className="min-h-11 rounded-2xl" asChild>
              <Link href="/admin/users/new">New account</Link>
            </Button>
          }
        />
      </div>

      <form
        className="admin-panel mb-5 grid gap-3 rounded-[1.5rem] bg-card p-4 shadow-sm ring-1 ring-foreground/5 sm:mb-6 sm:grid-cols-2 sm:p-5 lg:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(qDraft);
        }}
      >
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="user-q">Search</Label>
          <Input
            id="user-q"
            className="min-h-11 rounded-2xl"
            placeholder="Name or email"
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="user-role">Role</Label>
          <Select
            value={role}
            onValueChange={(value) => {
              if (value) setRole(value);
            }}
          >
            <SelectTrigger id="user-role" className="min-h-11 w-full rounded-2xl">
              <SelectValue placeholder="Role" />
            </SelectTrigger>
            <SelectContent>
              {ROLE_FILTERS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="user-active">Status</Label>
          <Select
            value={active}
            onValueChange={(value) => {
              if (value) setActive(value);
            }}
          >
            <SelectTrigger
              id="user-active"
              className="min-h-11 w-full rounded-2xl"
            >
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              {ACTIVE_FILTERS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end sm:col-span-2 lg:col-span-4">
          <Button type="submit" variant="outline" className="min-h-11 rounded-2xl">
            Apply search
          </Button>
        </div>
      </form>

      {loading && (
        <div className="space-y-3" role="status" aria-label="Loading">
          <Skeleton className="h-28 rounded-[1.5rem]" />
          <Skeleton className="h-28 rounded-[1.5rem]" />
        </div>
      )}

      <ApiErrorAlert error={error} className="mb-6" />

      {!loading && !error && (
        <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card shadow-sm ring-1 ring-foreground/5">
          {users.length === 0 ? (
            <p className="px-5 py-12 text-sm text-muted-foreground sm:px-6">
              No staff accounts match these filters.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="px-5 sm:px-6">Name</TableHead>
                  <TableHead className="hidden sm:table-cell">Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="pr-5 text-right sm:pr-6">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.userId}>
                    <TableCell className="px-5 font-medium sm:px-6">
                      {u.fullName}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      {u.email}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="rounded-full">
                        {u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {u.isActive ? (
                        <Badge variant="outline" className="rounded-full">
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="destructive" className="rounded-full">
                          Inactive
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="pr-5 text-right sm:pr-6">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="min-h-9 rounded-xl"
                          asChild
                        >
                          <Link href={`/admin/users/${u.userId}`}>Edit</Link>
                        </Button>
                        {u.isActive ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="min-h-9 rounded-xl"
                          disabled={pendingId === u.userId}
                          onClick={() => void setActiveState(u.userId, false)}
                        >
                          Deactivate
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="min-h-9 rounded-xl"
                          disabled={pendingId === u.userId}
                          onClick={() => void setActiveState(u.userId, true)}
                        >
                          Reactivate
                        </Button>
                      )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </PageShell>
  );
}
