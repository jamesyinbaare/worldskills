"use client";

import Link from "next/link";
import { FormEvent, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronRightIcon } from "lucide-react";
import { ApiError, CompetitionOut, ValidateOut, apiFetch, deleteGeneralCriteriaDocument, downloadGeneralCriteriaDocument, triggerBrowserDownload, updateCompetitionPublicProfile, uploadGeneralCriteriaDocument } from "@/lib/api";
import { RegistrationConfigCard } from "@/components/admin/RegistrationConfigCard";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

type WorkspaceTab = "overview" | "registration" | "profile";

type ModuleLink = {
  href: string;
  title: string;
  description: string;
};

function parseTab(value: string | null): WorkspaceTab {
  if (value === "registration" || value === "profile" || value === "overview") {
    return value;
  }
  return "overview";
}

function CycleMetaLine({
  cycle,
  competitionId,
}: {
  cycle: CompetitionOut;
  competitionId: string;
}) {
  const [copied, setCopied] = useState(false);
  const languages =
    cycle.languages && cycle.languages.length > 0
      ? cycle.languages.join(", ")
      : "—";

  async function copyId() {
    try {
      await navigator.clipboard.writeText(competitionId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
      <span>
        {cycle.period?.start} → {cycle.period?.end} · {cycle.timeZone} ·{" "}
        {languages}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs text-muted-foreground"
        onClick={copyId}
      >
        {copied ? "Copied" : "Copy ID"}
      </Button>
    </div>
  );
}

function ModuleNavSection({
  title,
  description,
  links,
}: {
  title: string;
  description: string;
  links: ModuleLink[];
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="overflow-hidden rounded-xl bg-background/60 ring-1 ring-foreground/10">
        <ul className="divide-y divide-border">
          {links.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className="flex min-h-11 items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/60 sm:px-5"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-foreground sm:text-base">
                    {item.title}
                  </span>
                  <span className="block text-sm text-muted-foreground">
                    {item.description}
                  </span>
                </span>
                <ChevronRightIcon
                  className="size-5 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function PublicProfilePanel({
  competitionId,
  cycle,
  onSaved,
}: {
  competitionId: string;
  cycle: CompetitionOut;
  onSaved: (cycle: CompetitionOut) => void;
}) {
  const [text, setText] = useState(cycle.description ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const criteriaInputRef = useRef<HTMLInputElement>(null);
  const [criteriaPending, setCriteriaPending] = useState(false);
  const [criteriaError, setCriteriaError] = useState<ApiError | null>(null);
  const [criteriaMessage, setCriteriaMessage] = useState<string | null>(null);

  useEffect(() => {
    setText(cycle.description ?? "");
  }, [cycle.description]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await updateCompetitionPublicProfile(competitionId, {
        description: text.trim() ? text.trim() : null,
      });
      onSaved(updated);
      setMessage("Public about text saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not save public profile",
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
    <div className="space-y-5">
      <div className="admin-panel space-y-6 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            Public profile
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            About text shown on the public competition page.
          </p>
        </div>
        <form onSubmit={onSave} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="publicDescription">About this competition</Label>
            <Textarea
              id="publicDescription"
              className="min-h-40"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={20000}
              placeholder="Describe the competition for competitors and institutions…"
              data-testid="cycle-public-description"
            />
          </div>
          <ApiErrorAlert error={error} title="Could not save" />
          {message ? (
            <p className="text-sm text-muted-foreground" role="status">
              {message}
            </p>
          ) : null}
          <Button
            type="submit"
            disabled={pending}
            className="min-h-11"
            data-testid="cycle-public-description-save"
          >
            {pending ? "Saving…" : "Save public profile"}
          </Button>
        </form>
      </div>

      <div className="admin-panel space-y-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            General criteria
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Optional competition-wide criteria document. Competitors can
            download it alongside skill-area criteria.
          </p>
        </div>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Document</dt>
            <dd className="font-medium">
              {cycle.generalCriteriaFileName ?? "None uploaded"}
            </dd>
          </div>
        </dl>
        <input
          ref={criteriaInputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            if (!file) return;
            void (async () => {
              setCriteriaPending(true);
              setCriteriaError(null);
              setCriteriaMessage(null);
              try {
                const updated = await uploadGeneralCriteriaDocument(
                  competitionId,
                  file,
                );
                onSaved(updated);
                setCriteriaMessage("General criteria document uploaded.");
              } catch (err) {
                if (err instanceof ApiError) setCriteriaError(err);
              } finally {
                setCriteriaPending(false);
                if (criteriaInputRef.current) {
                  criteriaInputRef.current.value = "";
                }
              }
            })();
          }}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={criteriaPending}
            onClick={() => criteriaInputRef.current?.click()}
            data-testid="general-criteria-upload"
          >
            {criteriaPending
              ? "Working…"
              : cycle.hasGeneralCriteriaDocument
                ? "Replace document"
                : "Upload document"}
          </Button>
          {cycle.hasGeneralCriteriaDocument ? (
            <>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11"
                disabled={criteriaPending}
                onClick={() => {
                  void (async () => {
                    setCriteriaPending(true);
                    setCriteriaError(null);
                    try {
                      const { blob, filename } =
                        await downloadGeneralCriteriaDocument(competitionId);
                      triggerBrowserDownload(blob, filename);
                    } catch (err) {
                      if (err instanceof ApiError) setCriteriaError(err);
                    } finally {
                      setCriteriaPending(false);
                    }
                  })();
                }}
                data-testid="general-criteria-download"
              >
                Download
              </Button>
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                disabled={criteriaPending}
                onClick={() => {
                  void (async () => {
                    setCriteriaPending(true);
                    setCriteriaError(null);
                    setCriteriaMessage(null);
                    try {
                      const updated =
                        await deleteGeneralCriteriaDocument(competitionId);
                      onSaved(updated);
                      setCriteriaMessage("General criteria document removed.");
                    } catch (err) {
                      if (err instanceof ApiError) setCriteriaError(err);
                    } finally {
                      setCriteriaPending(false);
                    }
                  })();
                }}
                data-testid="general-criteria-remove"
              >
                Remove
              </Button>
            </>
          ) : null}
        </div>
        <ApiErrorAlert error={criteriaError} title="General criteria" />
        {criteriaMessage ? (
          <Alert>
            <AlertTitle>Updated</AlertTitle>
            <AlertDescription>{criteriaMessage}</AlertDescription>
          </Alert>
        ) : null}
      </div>
    </div>
  );
}

function feedbackAlertTitle(message: string): string {
  if (message.startsWith("Validation passed")) return "Validation passed";
  if (message.startsWith("Validation ready")) return "Ready to activate";
  if (message.startsWith("Validation found")) return "Validation found issues";
  if (message.startsWith("Competition is")) return "Competition updated";
  return "Update";
}

function CompetitionWorkspacePageInner() {
  const params = useParams<{ id: string }>();
  const competitionId = params.id;
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [cycle, setCycle] = useState<CompetitionOut | null>(null);
  const [validation, setValidation] = useState<ValidateOut | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<WorkspaceTab>("overview");
  const [hashHandled, setHashHandled] = useState(false);

  const load = useCallback(async () => {
    const data = await apiFetch<CompetitionOut>(`/competitions/${competitionId}`);
    setCycle(data);
  }, [competitionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await load();
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Could not load cycle",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (!hashHandled && typeof window !== "undefined") {
      const hash = window.location.hash.slice(1);
      if (hash === "registration") {
        setTab("registration");
        setHashHandled(true);
        const params = new URLSearchParams(searchParams.toString());
        params.set("tab", "registration");
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname, {
          scroll: false,
        });
        return;
      }
      setHashHandled(true);
    }
    setTab(parseTab(searchParams.get("tab")));
  }, [searchParams, hashHandled, pathname, router]);

  function onTabChange(next: string) {
    const value = parseTab(next);
    setTab(value);
    const params = new URLSearchParams(searchParams.toString());
    if (value === "overview") {
      params.delete("tab");
    } else {
      params.set("tab", value);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const canActivate = validation?.ok === true;
  const activateBlocked = !canActivate;
  const advisoryIssues =
    validation?.issues.filter((i) => i.severity === "advisory") ?? [];
  const blockingIssues =
    validation?.issues.filter((i) => i.severity !== "advisory") ?? [];
  const canDeactivate =
    cycle?.status === "ACTIVE" || cycle?.status === "LOCKED";

  async function runValidate() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<ValidateOut>(`/competitions/${competitionId}:validate`, {
        method: "POST",
      });
      setValidation(result);
      const advisories = result.issues.filter((i) => i.severity === "advisory");
      setMessage(
        result.ok
          ? advisories.length > 0
            ? `Validation ready to activate with ${advisories.length} advisory warning(s).`
            : "Validation passed."
          : "Validation found issues.",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Validate failed",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function runActivate() {
    if (!canActivate) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<{ status: string }>(
        `/competitions/${competitionId}:activate`,
        { method: "POST" },
      );
      setMessage(`Competition is ${result.status}.`);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Activate failed",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function runDeactivate() {
    if (!canDeactivate) return;
    const confirmed = window.confirm(
      "Deactivate this competition? It will be marked CLOSED and will no longer appear as active.",
    );
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<{ status: string }>(
        `/competitions/${competitionId}:deactivate`,
        { method: "POST" },
      );
      setMessage(`Competition is ${result.status}.`);
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Deactivate failed",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function runClone() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<{ newCompetitionId: string }>(
        `/competitions/${competitionId}:clone`,
        { method: "POST" },
      );
      window.location.assign(`/admin/competitions/${result.newCompetitionId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Clone failed",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
      setBusy(false);
    }
  }

  const configureLinks: ModuleLink[] = [
    {
      href: `/admin/competitions/${competitionId}/skills`,
      title: "Skills",
      description: "Capacity, pathways, exercises, and experts",
    },
    {
      href: `/admin/competitions/${competitionId}/zones`,
      title: "Zones & Regions",
      description: "Zones and catalog region mapping",
    },
    {
      href: `/admin/competitors?competitionId=${competitionId}`,
      title: "Competitors",
      description: "Registered competitors by skill area",
    },
    {
      href: `/admin/competitions/${competitionId}/school-quotas`,
      title: "School quotas",
      description: "Per-skill registration limits for schools",
    },
  ];

  if (loadError && !cycle) {
    return (
      <PageShell width="wide" className="max-w-6xl space-y-4 px-0 py-0 sm:px-0 sm:py-0">
        <Button variant="ghost" size="sm" className="-ml-2 min-h-9" asChild>
          <Link href="/admin/competitions">Competitions</Link>
        </Button>
        <Alert variant="destructive">
          <AlertTitle>Could not load cycle</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  if (!cycle) {
    return (
      <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
        <div className="space-y-4" role="status" aria-label="Loading workspace">
          <Skeleton className="h-10 w-2/3 rounded-xl" />
          <Skeleton className="h-4 w-1/2 rounded-lg" />
          <Skeleton className="h-9 w-80 rounded-lg" />
          <Skeleton className="mt-2 h-48 w-full rounded-[1.5rem]" />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      width="wide"
      className="max-w-6xl space-y-6 px-0 py-0 sm:px-0 sm:py-0"
    >
      <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
        <PageHeader
          title={cycle.name || "Competition"}
          backHref="/admin/competitions"
          backLabel="Competitions"
          actions={
            <StatusBadge
              status={cycle.status}
              className="text-sm sm:text-base"
            />
          }
          className="mb-0"
        />
        <div className="mt-3">
          <CycleMetaLine cycle={cycle} competitionId={competitionId} />
        </div>
      </div>

      <Tabs value={tab} onValueChange={onTabChange} className="gap-5">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 rounded-2xl bg-muted/80 p-1.5 sm:w-fit">
          <TabsTrigger
            value="overview"
            className="min-h-10 rounded-xl px-4 data-[state=active]:shadow-sm"
          >
            Overview
          </TabsTrigger>
          <TabsTrigger
            value="registration"
            className="min-h-10 rounded-xl px-4 data-[state=active]:shadow-sm"
          >
            Registration
          </TabsTrigger>
          <TabsTrigger
            value="profile"
            className="min-h-10 rounded-xl px-4 data-[state=active]:shadow-sm"
          >
            Public profile
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-5 outline-none">
          <div className="admin-panel space-y-5 overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-foreground">
                Readiness
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Validate, activate, deactivate, or clone this competition.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="outline" disabled={busy} onClick={runValidate}>
                Validate
              </Button>
              <Button
                disabled={busy || activateBlocked}
                onClick={runActivate}
                title={
                  activateBlocked
                    ? "Run validation and resolve blocking issues before activating."
                    : undefined
                }
                aria-disabled={activateBlocked}
              >
                Activate
              </Button>
              {canDeactivate ? (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={runDeactivate}
                  data-testid="competition-deactivate"
                >
                  Deactivate
                </Button>
              ) : null}
              <Button variant="accent" disabled={busy} onClick={runClone}>
                Clone
              </Button>
            </div>

            {activateBlocked && (
              <p className="text-sm text-muted-foreground" role="status">
                {validation === null
                  ? "Run Validate before you can activate this competition."
                  : "Resolve blocking validation issues before activating. Pending exercises are warnings only."}
              </p>
            )}

            {message && (
              <Alert
                variant={
                  message.startsWith("Validation found") ? "destructive" : "default"
                }
              >
                <AlertTitle>{feedbackAlertTitle(message)}</AlertTitle>
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            <ApiErrorAlert error={error} title="Action failed" />

            {validation && (
              <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
                <div className="border-b border-border bg-muted/40 px-4 py-3">
                  <p className="text-sm font-medium text-foreground">
                    Validation result
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {validation.ok
                      ? advisoryIssues.length > 0
                        ? "Ready to activate. Advisory items below do not block activation."
                        : "Configuration is complete."
                      : "Fix the blocking issues below before activation."}
                  </p>
                </div>
                {validation.issues.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-muted-foreground">
                    No issues.
                  </p>
                ) : (
                  <>
                    {blockingIssues.map((issue, idx) => (
                      <div key={`blocking-${issue.entity}-${idx}`}>
                        {idx > 0 && <Separator />}
                        <div className="border-l-2 border-destructive px-4 py-3">
                          <p className="text-xs font-medium uppercase tracking-wide text-destructive">
                            Blocking
                          </p>
                          <p className="text-sm font-medium">
                            {issue.code}: {issue.message}
                          </p>
                          {issue.link ? (
                            <Button
                              variant="link"
                              className="h-auto px-0 text-sm"
                              asChild
                            >
                              <Link href={issue.link}>Fix</Link>
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                    {advisoryIssues.map((issue, idx) => (
                      <div key={`advisory-${issue.entity}-${idx}`}>
                        {(blockingIssues.length > 0 || idx > 0) && <Separator />}
                        <div className="border-l-2 border-brand-gold px-4 py-3">
                          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Advisory
                          </p>
                          <p className="text-sm font-medium">
                            {issue.code}: {issue.message}
                          </p>
                          {issue.link ? (
                            <Button
                              variant="link"
                              className="h-auto px-0 text-sm"
                              asChild
                            >
                              <Link href={issue.link}>Configure</Link>
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          <div className="admin-panel overflow-hidden rounded-[1.5rem] bg-card p-5 shadow-sm ring-1 ring-foreground/5 sm:p-7">
            <ModuleNavSection
              title="Configure competition"
              description="Skills, zones, competitors, and school quotas."
              links={configureLinks}
            />
          </div>
        </TabsContent>

        <TabsContent value="registration" className="outline-none">
          <RegistrationConfigCard competitionId={competitionId} />
        </TabsContent>

        <TabsContent value="profile" className="outline-none">
          <PublicProfilePanel
            competitionId={competitionId}
            cycle={cycle}
            onSaved={setCycle}
          />
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}

export default function CompetitionWorkspacePage() {
  return (
    <Suspense
      fallback={
        <PageShell width="wide" className="max-w-6xl px-0 py-0 sm:px-0 sm:py-0">
          <div className="space-y-4" role="status" aria-label="Loading workspace">
            <Skeleton className="h-10 w-2/3 rounded-xl" />
            <Skeleton className="h-4 w-1/2 rounded-lg" />
            <Skeleton className="h-9 w-80 rounded-lg" />
            <Skeleton className="mt-2 h-48 w-full rounded-[1.5rem]" />
          </div>
        </PageShell>
      }
    >
      <CompetitionWorkspacePageInner />
    </Suspense>
  );
}
