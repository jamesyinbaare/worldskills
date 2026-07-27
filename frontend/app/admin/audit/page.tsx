"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  ApiError,
  createDsar,
  fetchAuditLog,
  type AuditEventOut,
  type DsarJobOut,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function AdminAuditPage() {
  const [entity, setEntity] = useState("");
  const [actor, setActor] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  const [subjectId, setSubjectId] = useState("");
  const [dsarType, setDsarType] = useState("ACCESS");
  const [dsarOut, setDsarOut] = useState<DsarJobOut | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function onLoad(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const out = await fetchAuditLog({
        entity: entity.trim() || null,
        actor: actor.trim() || null,
        from: from ? new Date(from).toISOString() : null,
        to: to ? new Date(to).toISOString() : null,
        limit: 100,
      });
      setEvents(out.events);
    } catch (err) {
      setEvents([]);
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not load audit log",
                fields: [],
                traceId: "",
              },
            }),
      );
    } finally {
      setPending(false);
    }
  }

  async function onDsar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const out = await createDsar({
        subjectId: subjectId.trim(),
        type: dsarType,
      });
      setDsarOut(out);
    } catch (err) {
      setDsarOut(null);
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not process DSAR",
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
    <PageShell width="wide" className="space-y-6">
      <PageHeader
        title="Audit & governance"
        description="Read-only audit trail. Events are append-only — there is no edit or delete. Process data-subject requests below."
      />

      <ApiErrorAlert error={error} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Audit log</CardTitle>
          <CardDescription>
            Filter by entity id (or cycle id), actor user id, and time range.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={onLoad}
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
            noValidate
            data-testid="audit-filters"
          >
            <div className="space-y-2">
              <Label htmlFor="entity">Entity / competition ID</Label>
              <Input
                id="entity"
                className="min-h-11"
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                data-testid="audit-entity"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="actor">Actor user ID</Label>
              <Input
                id="actor"
                className="min-h-11"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                data-testid="audit-actor"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="from">From</Label>
              <Input
                id="from"
                type="datetime-local"
                className="min-h-11"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                data-testid="audit-from"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="to">To</Label>
              <Input
                id="to"
                type="datetime-local"
                className="min-h-11"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                data-testid="audit-to"
              />
            </div>
            <Button
              type="submit"
              className="min-h-11 sm:col-span-2 lg:col-span-4"
              disabled={pending}
              data-testid="audit-load"
            >
              {pending ? "Loading…" : "Load events"}
            </Button>
          </form>

          <div className="overflow-x-auto" data-testid="audit-table">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Timestamp</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium">Entity</th>
                  <th className="py-2 pr-3 font-medium">Actor</th>
                  <th className="py-2 font-medium">Sig</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr
                    key={ev.eventId}
                    className="border-b border-border/60"
                    data-testid="audit-row"
                  >
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {new Date(ev.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2 pr-3 font-medium">{ev.action}</td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {ev.entityType}:{ev.entityId}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {ev.actorId ?? "—"}
                    </td>
                    <td className="py-2">
                      {ev.signatureValid == null
                        ? "—"
                        : ev.signatureValid
                          ? "OK"
                          : "FAIL"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                No events loaded. Run a filter to query the append-only log.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Data-subject request</CardTitle>
          <CardDescription>
            Process ACCESS, ERASURE, or WITHDRAW for a competitor subject id.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onDsar} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="subjectId">Competitor subject ID</Label>
              <Input
                id="subjectId"
                className="min-h-11"
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
                required
                data-testid="dsar-subject-id"
              />
              <FieldMessage message={fieldErrors.subjectId} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dsarType">Type</Label>
              <select
                id="dsarType"
                className="flex min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm"
                value={dsarType}
                onChange={(e) => setDsarType(e.target.value)}
                data-testid="dsar-type"
              >
                <option value="ACCESS">ACCESS</option>
                <option value="ERASURE">ERASURE</option>
                <option value="WITHDRAW">WITHDRAW</option>
              </select>
            </div>
            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={pending}
              data-testid="dsar-submit"
            >
              Submit DSAR
            </Button>
          </form>
          {dsarOut ? (
            <Alert className="mt-4" data-testid="dsar-result">
              <AlertTitle className="flex items-center gap-2">
                Job <StatusBadge status={dsarOut.status} />
              </AlertTitle>
              <AlertDescription>
                <p className="font-mono text-xs">{dsarOut.jobId}</p>
                {dsarOut.resultSummary ? (
                  <p className="mt-2">{dsarOut.resultSummary}</p>
                ) : null}
                {dsarOut.export ? (
                  <Textarea
                    className="mt-3 font-mono text-xs"
                    readOnly
                    rows={8}
                    value={JSON.stringify(dsarOut.export, null, 2)}
                    data-testid="dsar-export"
                  />
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        <Link href="/admin/competitions" className="underline underline-offset-2">
          Back to cycles
        </Link>
      </p>
    </PageShell>
  );
}
