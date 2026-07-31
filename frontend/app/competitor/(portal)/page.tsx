"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRightIcon, TrophyIcon } from "lucide-react";
import {
  ApiError,
  competitionRegisterHref,
  downloadSkillCriteriaDocument,
  getMyStages,
  isDraftRegistrationStatus,
  listMyRegistrations,
  listOpenCompetitions,
  triggerBrowserDownload,
  type MyRegistrationOut,
  type MyStageOut,
  type MyStagesOut,
  type OpenCompetitionOut,
} from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { StatusBadge } from "@/components/layout/StatusBadge";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

type NextAction = {
  key: string;
  title: string;
  description: string;
  href: string;
  cta: string;
};

function stageCta(stage: MyStageOut): { label: string; hrefSuffix: string } | null {
  if (!stage.exerciseAvailable) return null;
  const state = stage.submission.state?.toUpperCase();
  if (state && ["ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"].includes(state)) {
    return { label: "View receipt", hrefSuffix: `/stages/${stage.stageId}/submit` };
  }
  if (state === "OPEN" || state === "UPLOADED" || state === "SCANNING" || state === "QUARANTINED") {
    return {
      label: "Continue submission",
      hrefSuffix: `/stages/${stage.stageId}/submit`,
    };
  }
  if (stage.windowStatus === "open" || stage.windowStatus === "unknown") {
    return {
      label: "View exercise & submit",
      hrefSuffix: `/stages/${stage.stageId}/submit`,
    };
  }
  return null;
}

function buildNextActions(
  registrations: MyRegistrationOut[],
  stageMaps: Record<string, MyStagesOut>,
): NextAction[] {
  const actions: NextAction[] = [];
  for (const reg of registrations) {
    if (reg.status?.toUpperCase() === "DRAFT") {
      actions.push({
        key: `draft-${reg.competitionId}`,
        title: "Continue application",
        description: `Finish your registration for ${reg.competitionName}.`,
        href: competitionRegisterHref(reg.competitionId),
        cta: "Continue application",
      });
      continue;
    }
    if (
      !reg.consentParticipationAt &&
      (reg.flags ?? []).some((f) => f.toUpperCase() === "CONSENT_PENDING")
    ) {
      actions.push({
        key: `consent-${reg.competitorId}`,
        title: "Guardian consent",
        description: `Optional: upload a signed consent form for ${reg.competitionName}.`,
        href: `/competitor/competitors/${reg.competitorId}/consent`,
        cta: "Open consent",
      });
    }
    const pathway = stageMaps[reg.competitionId];
    if (!pathway) continue;
    for (const stage of pathway.stages) {
      if (!stage.exerciseAvailable) continue;
      if (stage.windowStatus !== "open" && stage.windowStatus !== "unknown") continue;
      const locked =
        stage.submission.uploadLocked ||
        ["ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"].includes(
          (stage.submission.state || "").toUpperCase(),
        );
      const deadlineOpen = (() => {
        // Prefer stage closesAt from pathway; submission may not expose deadline here.
        if (!stage.closesAt) return !locked;
        const closes = new Date(stage.closesAt).getTime();
        if (Number.isNaN(closes)) return false;
        return closes > Date.now();
      })();
      if (locked && !deadlineOpen) continue;
      const cta = stageCta(stage);
      if (!cta) continue;
      actions.push({
        key: `stage-${stage.stageId}`,
        title: stage.exerciseTitle || stage.name,
        description: `${reg.competitionName} · Stage ${stage.order} · ${reg.skillName}`,
        href: `/competitor/competitions/${reg.competitionId}${cta.hrefSuffix}`,
        cta: locked && deadlineOpen ? "Update submission" : cta.label,
      });
    }
  }
  return actions.slice(0, 6);
}

function formatRegistrationWindow(
  window?: { opensAt: string; closesAt: string } | null,
): string | null {
  if (!window?.closesAt) return null;
  const closes = new Date(window.closesAt);
  if (Number.isNaN(closes.getTime())) return null;
  return `Closes ${closes.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })}`;
}

function OpenCompetitionCards({
  cycles,
  registeredIds,
  draftIds,
}: {
  cycles: OpenCompetitionOut[];
  registeredIds: Set<string>;
  draftIds?: Set<string>;
}) {
  return (
    <ul className="space-y-3">
      {cycles.map((c) => {
        const windowLabel = formatRegistrationWindow(c.window);
        const isDraft = draftIds?.has(c.competitionId) ?? false;
        const alreadyRegistered =
          registeredIds.has(c.competitionId) && !isDraft;
        return (
          <li key={c.competitionId}>
            <Card className="border-border/80 shadow-sm">
              <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
                    <TrophyIcon className="size-5" aria-hidden />
                  </span>
                  <div className="min-w-0 space-y-1">
                    <h3 className="text-base font-semibold leading-snug">
                      {c.name}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {isDraft
                        ? "Draft application in progress"
                        : alreadyRegistered
                          ? "You are already registered"
                          : (windowLabel ?? "Registration window open")}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
                  {isDraft ? (
                    <Button
                      size="lg"
                      className="min-h-12 w-full gap-2 sm:w-auto sm:min-w-44"
                      asChild
                    >
                      <Link
                        href={competitionRegisterHref(c.competitionId)}
                        data-testid={`competitor-continue-draft-${c.competitionId}`}
                      >
                        Continue application
                        <ArrowRightIcon
                          className="size-4 opacity-70"
                          aria-hidden
                        />
                      </Link>
                    </Button>
                  ) : alreadyRegistered ? (
                    <Button
                      size="lg"
                      className="min-h-12 w-full gap-2 sm:w-auto sm:min-w-44"
                      asChild
                    >
                      <Link
                        href={`/competitor/competitions/${c.competitionId}`}
                        data-testid={`competitor-open-${c.competitionId}`}
                      >
                        Go to competition
                        <ArrowRightIcon
                          className="size-4 opacity-70"
                          aria-hidden
                        />
                      </Link>
                    </Button>
                  ) : (
                    <Button
                      size="lg"
                      className="min-h-12 w-full gap-2 sm:w-auto sm:min-w-44"
                      asChild
                    >
                      <Link
                        href={competitionRegisterHref(c.competitionId)}
                        data-testid={`competitor-register-${c.competitionId}`}
                      >
                        Register
                        <ArrowRightIcon
                          className="size-4 opacity-70"
                          aria-hidden
                        />
                      </Link>
                    </Button>
                  )}
                  <Button
                    size="lg"
                    variant="outline"
                    className="min-h-12 w-full sm:w-auto"
                    asChild
                  >
                    <Link href={`/competitions/${c.competitionId}`}>
                      View details
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function RegisteredOverview({
  registrations,
}: {
  registrations: MyRegistrationOut[];
}) {
  const [stageMaps, setStageMaps] = useState<Record<string, MyStagesOut>>({});
  const [loadingStages, setLoadingStages] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [criteriaPendingId, setCriteriaPendingId] = useState<string | null>(
    null,
  );
  const [openCycles, setOpenCycles] = useState<OpenCompetitionOut[]>([]);
  const [loadingCycles, setLoadingCycles] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoadingStages(true);
      try {
        const activeRegs = registrations.filter(
          (reg) => reg.status?.toUpperCase() !== "DRAFT",
        );
        const entries = await Promise.all(
          activeRegs.map(async (reg) => {
            const stages = await getMyStages(reg.competitionId);
            return [reg.competitionId, stages] as const;
          }),
        );
        if (!cancelled) {
          setStageMaps(Object.fromEntries(entries));
          setError(null);
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoadingStages(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [registrations]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoadingCycles(true);
      try {
        const cycles = await listOpenCompetitions();
        if (!cancelled) setOpenCycles(cycles);
      } catch {
        if (!cancelled) setOpenCycles([]);
      } finally {
        if (!cancelled) setLoadingCycles(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const nextActions = buildNextActions(registrations, stageMaps);
  const draftIds = new Set(
    registrations
      .filter((r) => r.status?.toUpperCase() === "DRAFT")
      .map((r) => r.competitionId),
  );
  const registeredIds = new Set(
    registrations
      .filter((r) => r.status?.toUpperCase() !== "DRAFT")
      .map((r) => r.competitionId),
  );

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title="Your dashboard"
        description="Jump into open stage exercises, track submissions, and manage your account."
      />
      <ApiErrorAlert error={error} title="Could not load stages" />

      <section className="space-y-3" data-testid="competitor-next-actions">
        <h2 className="text-lg font-semibold">Next actions</h2>
        {loadingStages ? (
          <p className="text-sm text-muted-foreground">Checking your stages…</p>
        ) : null}
        {!loadingStages && nextActions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing needs your attention right now. Open a competition to review
            your stage pathway.
          </p>
        ) : null}
        <ul className="grid gap-3 sm:grid-cols-2">
          {nextActions.map((action) => (
            <li key={action.key}>
              <Card className="h-full">
                <CardHeader className="pb-2">
                  <h3 className="font-semibold leading-snug">{action.title}</h3>
                  <CardDescription>{action.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button className="min-h-11" asChild>
                    <Link href={action.href}>{action.cta}</Link>
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3" data-testid="competitor-my-competitions">
        <h2 className="text-lg font-semibold">My competitions</h2>
        <ul className="space-y-3">
          {registrations.map((reg) => {
            const isDraft = reg.status?.toUpperCase() === "DRAFT";
            const pathway = stageMaps[reg.competitionId];
            const openCount =
              pathway?.stages.filter(
                (s) =>
                  s.exerciseAvailable &&
                  (s.windowStatus === "open" || s.windowStatus === "unknown"),
              ).length ?? 0;
            return (
              <li key={reg.competitorId}>
                <Card>
                  <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
                    <div className="min-w-0 space-y-1">
                      <h3 className="truncate text-base font-semibold">
                        {reg.competitionName}
                      </h3>
                      <CardDescription>
                        {isDraft
                          ? "Draft application"
                          : reg.skillName}
                        {!isDraft && openCount > 0
                          ? ` · ${openCount} open stage${openCount === 1 ? "" : "s"}`
                          : null}
                      </CardDescription>
                    </div>
                    <StatusBadge status={reg.status} />
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-2">
                    {isDraft ? (
                      <Button
                        className="min-h-11"
                        asChild
                        data-testid={`continue-draft-${reg.competitionId}`}
                      >
                        <Link
                          href={competitionRegisterHref(reg.competitionId)}
                        >
                          Continue application
                        </Link>
                      </Button>
                    ) : (
                      <Button
                        variant="secondary"
                        className="min-h-11"
                        asChild
                        data-testid={`open-competition-${reg.competitionId}`}
                      >
                        <Link
                          href={`/competitor/competitions/${reg.competitionId}`}
                        >
                          View stages
                        </Link>
                      </Button>
                    )}
                    {!isDraft && reg.hasCriteriaDocument && reg.skillId ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11"
                        disabled={criteriaPendingId === reg.skillId}
                        data-testid={`download-criteria-${reg.skillId}`}
                        onClick={() => {
                          const skillId = reg.skillId;
                          if (!skillId) return;
                          void (async () => {
                            setCriteriaPendingId(skillId);
                            setError(null);
                            try {
                              const { blob, filename } =
                                await downloadSkillCriteriaDocument(
                                  reg.competitionId,
                                  skillId,
                                );
                              triggerBrowserDownload(blob, filename);
                            } catch (err) {
                              if (err instanceof ApiError) setError(err);
                            } finally {
                              setCriteriaPendingId(null);
                            }
                          })();
                        }}
                      >
                        {criteriaPendingId === reg.skillId
                          ? "Downloading…"
                          : "Download criteria"}
                      </Button>
                    ) : null}
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="space-y-4" data-testid="competitor-open-competitions">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Open for registration</h2>
          <p className="text-sm text-muted-foreground">
            Active competitions with an open registration window.
          </p>
        </div>

        {loadingCycles ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading competitions…
          </p>
        ) : null}

        {!loadingCycles && openCycles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No competitions are open for registration right now.
          </p>
        ) : null}

        {!loadingCycles && openCycles.length > 0 ? (
          <OpenCompetitionCards
            cycles={openCycles}
            registeredIds={registeredIds}
            draftIds={draftIds}
          />
        ) : null}
      </section>
    </PageShell>
  );
}

function UnregisteredHub() {
  const [openCycles, setOpenCycles] = useState<OpenCompetitionOut[]>([]);
  const [loadingCycles, setLoadingCycles] = useState(true);
  const [cyclesError, setCyclesError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoadingCycles(true);
      try {
        const cycles = await listOpenCompetitions();
        if (!cancelled) {
          setOpenCycles(cycles);
          setCyclesError(null);
        }
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setCyclesError(err);
        }
      } finally {
        if (!cancelled) setLoadingCycles(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageShell width="wide" className="space-y-8">
      <PageHeader
        title="Register for a competition"
        description="Pick an open competition to start registration and unlock stage exercises."
      />

      <section className="space-y-4" data-testid="competitor-open-competitions">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Open for registration</h2>
          <p className="text-sm text-muted-foreground">
            Active competitions with an open registration window.
          </p>
        </div>

        {loadingCycles ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading competitions…
          </p>
        ) : null}
        <ApiErrorAlert error={cyclesError} title="Could not load competitions" />

        {!loadingCycles && openCycles.length === 0 && !cyclesError ? (
          <Card>
            <CardContent className="space-y-2 py-8">
              <p className="font-medium">Nothing open right now</p>
              <p className="text-sm text-muted-foreground">
                When registration opens, competitions appear here. Check back
                soon.
              </p>
            </CardContent>
          </Card>
        ) : null}

        {!loadingCycles && openCycles.length > 0 ? (
          <OpenCompetitionCards
            cycles={openCycles}
            registeredIds={new Set()}
          />
        ) : null}
      </section>
    </PageShell>
  );
}

export default function CompetitorHomePage() {
  const router = useRouter();
  const [registrations, setRegistrations] = useState<MyRegistrationOut[] | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [resumingDraft, setResumingDraft] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;

        const drafts = rows.filter((r) => isDraftRegistrationStatus(r.status));
        const submitted = rows.filter(
          (r) => !isDraftRegistrationStatus(r.status),
        );
        // Incomplete registration only: resume wizard instead of dashboard.
        if (drafts.length > 0 && submitted.length === 0) {
          setResumingDraft(true);
          router.replace(competitionRegisterHref(drafts[0].competitionId));
          return;
        }

        setRegistrations(rows);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setRegistrations([]);
          if (err instanceof ApiError) setError(err);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (resumingDraft || registrations === null) {
    return (
      <PageShell width="narrow" className="space-y-6">
        <p className="text-sm text-muted-foreground" role="status">
          {resumingDraft
            ? "Continuing your application…"
            : "Loading…"}
        </p>
      </PageShell>
    );
  }

  if (registrations.length > 0) {
    return <RegisteredOverview registrations={registrations} />;
  }

  if (error) {
    return (
      <PageShell width="narrow" className="space-y-6">
        <PageHeader
          title="Register for a competition"
          description="Pick an open competition to start registration and unlock stage exercises."
        />
        <ApiErrorAlert error={error} title="Could not load your registrations" />
      </PageShell>
    );
  }

  return <UnregisteredHub />;
}
