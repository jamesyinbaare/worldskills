"use client";

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  ScheduleSessionListItem,
  VenueOut,
  assignScheduleSlot,
  createScheduleSession,
  listScheduleSessions,
  listVenues,
  recordScheduleIncident,
} from "@/lib/api";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
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

function SchedulePageInner() {
  const { filters } = useCompetitionSkillQuery();
  const competitionId = filters.competitionId;

  const [rows, setRows] = useState<ScheduleSessionListItem[]>([]);
  const [venues, setVenues] = useState<VenueOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [createOpen, setCreateOpen] = useState(false);
  const [venueId, setVenueId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [workstations, setWorkstations] = useState("10");

  const [assignOpen, setAssignOpen] = useState(false);
  const [assignSessionId, setAssignSessionId] = useState("");
  const [competitorId, setCompetitorId] = useState("");
  const [workstation, setWorkstation] = useState("");

  const [incidentOpen, setIncidentOpen] = useState(false);
  const [incidentSessionId, setIncidentSessionId] = useState("");
  const [incidentSummary, setIncidentSummary] = useState("");
  const [severity, setSeverity] = useState("");

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    if (!competitionId) {
      setRows([]);
      setVenues([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [sessions, venueList] = await Promise.all([
          listScheduleSessions(competitionId, {
            skillId: filters.skillId || null,
            q: filters.q || null,
          }),
          listVenues(competitionId),
        ]);
        if (!cancelled) {
          setRows(sessions);
          setVenues(venueList);
        }
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

  async function onCreateSession(e: FormEvent) {
    e.preventDefault();
    if (!competitionId) return;
    setPending(true);
    setError(null);
    try {
      await createScheduleSession(competitionId, {
        venueId,
        startsAt: new Date(startsAt).toISOString(),
        endsAt: new Date(endsAt).toISOString(),
        workstations: Number(workstations),
      });
      setCreateOpen(false);
      setStatusMessage("Session created.");
      refresh();
    } catch (err) {
      captureErr(err, "Could not create session");
    } finally {
      setPending(false);
    }
  }

  async function onAssign(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const out = await assignScheduleSlot(assignSessionId, {
        competitorId: competitorId.trim(),
        workstation: workstation.trim(),
      });
      setAssignOpen(false);
      setStatusMessage(`Assigned workstation ${out.workstation}.`);
      refresh();
    } catch (err) {
      captureErr(err, "Could not assign workstation");
    } finally {
      setPending(false);
    }
  }

  async function onIncident(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await recordScheduleIncident(incidentSessionId, {
        summary: incidentSummary.trim(),
        severity: severity.trim() || null,
      });
      setIncidentOpen(false);
      setStatusMessage("Incident recorded.");
      refresh();
    } catch (err) {
      captureErr(err, "Could not record incident");
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="wide" className="max-w-6xl space-y-5 px-0 py-0 sm:px-0 sm:py-0">
      <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          className="mb-0"
          title="Schedule"
          description="Sessions, slots, and incidents — scoped by competition and skill area."
          actions={
            <Button
              className="min-h-11 rounded-2xl"
              disabled={!competitionId}
              onClick={() => {
                setVenueId(venues[0]?.venueId ?? "");
                setCreateOpen(true);
              }}
            >
              Create session
            </Button>
          }
        />
      </div>

      <RunCompetitionFilterBar searchPlaceholder="Search venue or state…" />

      {statusMessage ? (
        <Alert>
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{statusMessage}</AlertDescription>
        </Alert>
      ) : null}
      <ApiErrorAlert error={error} />

      {!competitionId ? (
        <p className="text-sm text-muted-foreground">
          Select a competition to view and manage schedule sessions.
        </p>
      ) : loading ? (
        <Skeleton className="h-48 w-full rounded-2xl" />
      ) : (
        <div className="overflow-hidden rounded-[1.25rem] bg-card shadow-sm ring-1 ring-foreground/5">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Venue</TableHead>
                <TableHead>Window</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="text-right">Slots</TableHead>
                <TableHead className="text-right">Incidents</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                    No sessions match these filters.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => (
                  <TableRow key={row.sessionId}>
                    <TableCell className="font-medium">{row.venueName}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(row.startsAt).toLocaleString()} –{" "}
                      {new Date(row.endsAt).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.state} />
                    </TableCell>
                    <TableCell className="text-right">
                      {row.assignmentCount}/{row.workstations}
                    </TableCell>
                    <TableCell className="text-right">{row.incidentCount}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-xl"
                          onClick={() => {
                            setAssignSessionId(row.sessionId);
                            setCompetitorId("");
                            setWorkstation("");
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
                            setIncidentSessionId(row.sessionId);
                            setIncidentSummary("");
                            setSeverity("");
                            setIncidentOpen(true);
                          }}
                        >
                          Incident
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

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create session</DialogTitle>
            <DialogDescription>
              Choose a venue and window. Capacity cannot exceed the venue.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onCreateSession} className="space-y-4">
            <div className="space-y-2">
              <Label>Venue</Label>
              <Select value={venueId} onValueChange={setVenueId}>
                <SelectTrigger className="min-h-10">
                  <SelectValue placeholder="Select venue" />
                </SelectTrigger>
                <SelectContent>
                  {venues.map((v) => (
                    <SelectItem key={v.venueId} value={v.venueId}>
                      {v.name} (cap {v.capacity})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="startsAt">Starts at</Label>
                <Input
                  id="startsAt"
                  type="datetime-local"
                  value={startsAt}
                  onChange={(e) => setStartsAt(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="endsAt">Ends at</Label>
                <Input
                  id="endsAt"
                  type="datetime-local"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value)}
                  required
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="workstations">Workstations</Label>
              <Input
                id="workstations"
                type="number"
                min={1}
                value={workstations}
                onChange={(e) => setWorkstations(e.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending || !venueId}>
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign workstation</DialogTitle>
            <DialogDescription>
              Assign a confirmed shortlisted competitor to a workstation.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onAssign} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="competitorId">Competitor ID</Label>
              <Input
                id="competitorId"
                value={competitorId}
                onChange={(e) => setCompetitorId(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="workstation">Workstation</Label>
              <Input
                id="workstation"
                value={workstation}
                onChange={(e) => setWorkstation(e.target.value)}
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

      <Dialog open={incidentOpen} onOpenChange={setIncidentOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record incident</DialogTitle>
          </DialogHeader>
          <form onSubmit={onIncident} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="summary">Summary</Label>
              <Textarea
                id="summary"
                value={incidentSummary}
                onChange={(e) => setIncidentSummary(e.target.value)}
                required
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="severity">Severity (optional)</Label>
              <Input
                id="severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={pending}>
                Record
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

export default function AdminScheduleHubPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full rounded-2xl" />}>
      <SchedulePageInner />
    </Suspense>
  );
}
