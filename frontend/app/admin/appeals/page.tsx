"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  AppealListItem,
  assignAppeal,
  disqualifyCompetitor,
  listAppeals,
  ruleAppeal,
} from "@/lib/api";
import { ApiErrorAlert, fieldErrorMap } from "@/components/forms/ApiErrorAlert";
import {
  RunCompetitionFilterBar,
  useCompetitionSkillQuery,
} from "@/components/admin/run/useCompetitionSkillQuery";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

function AppealsPageInner() {
  const { filters } = useCompetitionSkillQuery();
  const competitionId = filters.competitionId;

  const [rows, setRows] = useState<AppealListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [assignOpen, setAssignOpen] = useState(false);
  const [assignAppealId, setAssignAppealId] = useState("");
  const [officerId, setOfficerId] = useState("");

  const [ruleOpen, setRuleOpen] = useState(false);
  const [ruleAppealId, setRuleAppealId] = useState("");
  const [outcome, setOutcome] = useState("UPHELD");
  const [ruleReason, setRuleReason] = useState("");
  const [remedy, setRemedy] = useState("");

  const [dqOpen, setDqOpen] = useState(false);
  const [dqCompetitorId, setDqCompetitorId] = useState("");
  const [dqReason, setDqReason] = useState("");

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    if (!competitionId) {
      setRows([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const list = await listAppeals(competitionId, {
          skillId: filters.skillId || null,
          q: filters.q || null,
        });
        if (!cancelled) setRows(list);
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, filters.skillId, filters.q, reloadKey]);

  function captureErr(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setError(err);
      setFieldErrors(fieldErrorMap(err.fields));
    } else {
      setError(
        new ApiError(0, {
          error: {
            code: "HTTP_ERROR",
            message: fallback,
            fields: [],
            traceId: "",
          },
        }),
      );
    }
  }

  async function onAssign(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await assignAppeal(assignAppealId, officerId.trim());
      setAssignOpen(false);
      setStatusMessage(`Appeal assigned — state ${out.state}.`);
      refresh();
    } catch (err) {
      captureErr(err, "Could not assign appeal");
    } finally {
      setPending(false);
    }
  }

  async function onRule(e: FormEvent) {
    e.preventDefault();
    if (!ruleReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await ruleAppeal(ruleAppealId, {
        outcome,
        reason: ruleReason.trim(),
        remedy: remedy.trim() || null,
      });
      setRuleOpen(false);
      setStatusMessage(`Ruling saved — ${out.rulingOutcome ?? out.state}.`);
      refresh();
    } catch (err) {
      captureErr(err, "Could not rule on appeal");
    } finally {
      setPending(false);
    }
  }

  async function onDisqualify(e: FormEvent) {
    e.preventDefault();
    if (!dqReason.trim()) {
      setFieldErrors({ reason: "REASON_REQUIRED" });
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      const out = await disqualifyCompetitor(
        dqCompetitorId.trim(),
        dqReason.trim(),
      );
      setDqOpen(false);
      setStatusMessage(`Competitor disqualified (${out.status}).`);
      refresh();
    } catch (err) {
      captureErr(err, "Could not disqualify competitor");
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="wide" className="max-w-6xl space-y-5 px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Appeals"
          description="Assign officers and rule appeals — scoped by competition and skill area."
          actions={
            <Button
              className="min-h-11 rounded-2xl"
              variant="outline"
              disabled={!competitionId}
              onClick={() => {
                setDqCompetitorId("");
                setDqReason("");
                setDqOpen(true);
              }}
            >
              Disqualify
            </Button>
          }
        />
      </div>

      <RunCompetitionFilterBar searchPlaceholder="Search competitor, skill, or reason…" />

      {statusMessage ? (
        <Alert>
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}
      <ApiErrorAlert error={error} />

      {!competitionId ? (
        <p className="text-sm text-muted-foreground">
          Select a competition to view the appeals inbox.
        </p>
      ) : loading ? (
        <Skeleton className="h-48 w-full rounded-2xl" />
      ) : (
        <div className="overflow-hidden rounded-[1.25rem] bg-card shadow-sm ring-1 ring-foreground/5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Competitor</TableHead>
                <TableHead>Skill / Stage</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Submitted</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                    No appeals match these filters.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.appealId}>
                    <TableCell>
                      <div className="font-medium">
                        {row.competitorName || row.competitorRef || "—"}
                      </div>
                      {row.competitorRef ? (
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.competitorRef}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <div>{row.skillName || "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.stageName || ""}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.state} />
                    </TableCell>
                    <TableCell className="max-w-[14rem] truncate text-sm">
                      {row.reason}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.submittedAt
                        ? new Date(row.submittedAt).toLocaleString()
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-xl"
                          onClick={() => {
                            setAssignAppealId(row.appealId);
                            setOfficerId("");
                            setAssignOpen(true);
                          }}
                        >
                          Assign
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-xl"
                          onClick={() => {
                            setRuleAppealId(row.appealId);
                            setOutcome("UPHELD");
                            setRuleReason("");
                            setRemedy("");
                            setRuleOpen(true);
                          }}
                        >
                          Rule
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign officer</DialogTitle>
            <DialogDescription>
              Conflicted officers are rejected by the API.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onAssign} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="officerId">Officer user ID</Label>
              <Input
                id="officerId"
                value={officerId}
                onChange={(e) => setOfficerId(e.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending}>
                Assign
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={ruleOpen} onOpenChange={setRuleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rule on appeal</DialogTitle>
          </DialogHeader>
          <form onSubmit={onRule} className="space-y-4">
            <div className="space-y-2">
              <Label>Outcome</Label>
              <Select value={outcome} onValueChange={setOutcome}>
                <SelectTrigger className="min-h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="UPHELD">UPHELD</SelectItem>
                  <SelectItem value="DISMISSED">DISMISSED</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ruleReason">Reason</Label>
              <Textarea
                id="ruleReason"
                value={ruleReason}
                onChange={(e) => setRuleReason(e.target.value)}
                required
                rows={3}
              />
              {fieldErrors.reason ? (
                <p className="text-sm text-destructive">{fieldErrors.reason}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="remedy">Remedy (optional)</Label>
              <Input
                id="remedy"
                value={remedy}
                onChange={(e) => setRemedy(e.target.value)}
                placeholder="RE_SCORE | RE_RANK | REINSTATE"
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending}>
                Save ruling
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dqOpen} onOpenChange={setDqOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disqualify competitor</DialogTitle>
          </DialogHeader>
          <form onSubmit={onDisqualify} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dqCompetitorId">Competitor ID</Label>
              <Input
                id="dqCompetitorId"
                value={dqCompetitorId}
                onChange={(e) => setDqCompetitorId(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dqReason">Reason</Label>
              <Textarea
                id="dqReason"
                value={dqReason}
                onChange={(e) => setDqReason(e.target.value)}
                required
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button type="submit" variant="destructive" disabled={pending}>
                Disqualify
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

export default function AdminAppealsHubPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <AppealsPageInner />
    </Suspense>
  );
}
