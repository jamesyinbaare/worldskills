"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRightIcon,
  ChevronLeftIcon,
  DownloadIcon,
} from "lucide-react";
import { useParams } from "next/navigation";
import {
  ApiError,
  downloadPublicGeneralCriteriaDocument,
  downloadPublicSkillCriteriaDocument,
  fetchPublicSponsorLogo,
  getPublicCompetition,
  isCompetitorRole,
  listMyRegistrations,
  triggerBrowserDownload,
  type PublicCompetitionOut,
  type PublicSkillOut,
  type SponsorOut,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  skillCoverPalette,
  skillDetailHref,
} from "@/components/competitions/SkillAreasCarousel";
import {
  formatCompetitionDate,
  registerPath,
  signupNextHref,
} from "@/components/competitions/format";
import { ApiErrorAlert } from "@/components/forms/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function SkillSponsorLogo({
  sponsor,
}: {
  sponsor: SponsorOut;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!sponsor.hasLogo) {
      setSrc(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const { blob } = await fetchPublicSponsorLogo(sponsor.sponsorId);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setSrc(null);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sponsor.sponsorId, sponsor.hasLogo]);

  if (!sponsor.hasLogo || !src) {
    return (
      <span
        className="flex size-10 items-center justify-center rounded-lg bg-muted text-xs font-semibold text-muted-foreground"
        aria-hidden
      >
        {sponsor.name.slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- blob: from public API
    <img
      src={src}
      alt=""
      className="size-10 rounded-lg bg-white object-contain ring-1 ring-border"
    />
  );
}

function SkillSponsorsStrip({ sponsors }: { sponsors: SponsorOut[] }) {
  if (sponsors.length === 0) return null;

  return (
    <section
      className="space-y-3"
      aria-labelledby="skill-sponsors-heading"
    >
      <h2
        id="skill-sponsors-heading"
        className="text-lg font-semibold tracking-tight text-foreground"
      >
        Supported by
      </h2>
      <ul className="flex flex-wrap gap-3">
        {sponsors.map((sponsor) => {
          const inner = (
            <>
              <SkillSponsorLogo sponsor={sponsor} />
              <span className="min-w-0 truncate text-sm font-medium text-foreground">
                {sponsor.name}
              </span>
            </>
          );
          const className =
            "inline-flex max-w-full items-center gap-2.5 rounded-xl bg-card px-3 py-2 ring-1 ring-border transition hover:ring-brand-blue/30";

          if (sponsor.website) {
            return (
              <li key={sponsor.sponsorId}>
                <a
                  href={sponsor.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={className}
                  aria-label={`${sponsor.name} (opens website)`}
                >
                  {inner}
                </a>
              </li>
            );
          }

          return (
            <li key={sponsor.sponsorId}>
              <div className={className}>{inner}</div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function SkillAreaDetailPage() {
  const params = useParams<{ competitionId: string; skillId: string }>();
  const competitionId = params.competitionId;
  const skillId = params.skillId;
  const { status, me } = useAuth();

  const [cycle, setCycle] = useState<PublicCompetitionOut | null>(null);
  const [skill, setSkill] = useState<PublicSkillOut | null>(null);
  const [skillIndex, setSkillIndex] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadPending, setDownloadPending] = useState<
    "general" | "skill" | null
  >(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await getPublicCompetition(competitionId);
        if (cancelled) return;
        const match =
          data.skills.find((s) => s.skillId === skillId) ?? null;
        setCycle(data);
        setSkill(match);
        setSkillIndex(
          Math.max(
            0,
            data.skills.findIndex((s) => s.skillId === skillId),
          ),
        );
        setError(
          match
            ? null
            : new ApiError(404, {
                error: {
                  code: "SKILL_NOT_FOUND",
                  message: "This skill area is not available for registration.",
                  fields: [],
                  traceId: "",
                },
              }),
        );
      } catch (err) {
        if (!cancelled && err instanceof ApiError) {
          setError(err);
          setCycle(null);
          setSkill(null);
        } else if (!cancelled) {
          setError(
            new ApiError(0, {
              error: {
                code: "HTTP_ERROR",
                message: "Could not load skill area",
                fields: [],
                traceId: "",
              },
            }),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId, skillId]);

  useEffect(() => {
    if (status !== "authenticated" || !isCompetitorRole(me?.role ?? "")) {
      setAlreadyRegistered(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        setAlreadyRegistered(
          rows.some((r) => r.competitionId === competitionId),
        );
      } catch {
        if (!cancelled) setAlreadyRegistered(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, me?.role, competitionId]);

  const competitorRegister = registerPath(
    "competitor",
    competitionId,
    skillId,
  );
  const competitorDashboard = `/competitor/competitions/${competitionId}`;

  const startRegistrationHref = useMemo(() => {
    if (alreadyRegistered) return competitorDashboard;
    if (status === "authenticated" && isCompetitorRole(me?.role ?? "")) {
      return competitorRegister;
    }
    return signupNextHref(competitorRegister);
  }, [
    alreadyRegistered,
    competitorDashboard,
    competitorRegister,
    me?.role,
    status,
  ]);

  const startRegistrationLabel = alreadyRegistered
    ? "Go to my competition"
    : status === "authenticated" && isCompetitorRole(me?.role ?? "")
      ? "Continue registration"
      : "Start registration";

  async function onDownloadSkillCriteria() {
    if (!skill) return;
    setDownloadPending("skill");
    setDownloadError(null);
    try {
      const { blob, filename } = await downloadPublicSkillCriteriaDocument(
        competitionId,
        skill.skillId,
      );
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError
          ? err.message
          : "Could not download skill-area criteria.",
      );
    } finally {
      setDownloadPending(null);
    }
  }

  async function onDownloadGeneralCriteria() {
    setDownloadPending("general");
    setDownloadError(null);
    try {
      const { blob, filename } =
        await downloadPublicGeneralCriteriaDocument(competitionId);
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError
          ? err.message
          : "Could not download general criteria.",
      );
    } finally {
      setDownloadPending(null);
    }
  }

  const palette = skill
    ? skillCoverPalette(skill.skillId, skillIndex)
    : skillCoverPalette(skillId, 0);
  const meta = skill
    ? [
        skill.number ? `Skill ${skill.number}` : null,
        skill.familyName?.trim() || null,
      ]
        .filter(Boolean)
        .join(" · ")
    : null;
  const about =
    skill?.description?.trim() ||
    cycle?.description?.trim() ||
    (skill
      ? `${skill.name} is a skill area in ${cycle?.name ?? "this competition"}. Review the criteria document and register when you are ready to compete.`
      : null);
  const skillsBack =
    cycle && cycle.skills.length >= 2
      ? `/competitions/${competitionId}/skills`
      : "/competitions";

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-12 lg:py-16">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 mb-6 min-h-10 gap-1 text-muted-foreground"
          asChild
        >
          <Link href={skillsBack}>
            <ChevronLeftIcon className="size-4" aria-hidden />
            {cycle && cycle.skills.length >= 2
              ? "Back to skill areas"
              : "Back to competitions"}
          </Link>
        </Button>

        {loading ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading skill area…
          </p>
        ) : null}

        <ApiErrorAlert error={error} title="Skill area unavailable" />

        {error && !skill ? (
          <Alert variant="destructive" className="mt-4">
            <AlertTitle>Not available</AlertTitle>
            <AlertDescription>
              This skill area is not open for registration right now.
            </AlertDescription>
          </Alert>
        ) : null}

        {skill && cycle ? (
          <div className="animate-comp-fade grid gap-8 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)] lg:gap-12">
            <div className="mx-auto w-full max-w-[17rem] lg:mx-0">
              <div
                className={cn(
                  "relative aspect-3/4 overflow-hidden rounded-[1.75rem] shadow-[0_28px_56px_-28px_rgba(0,25,60,0.65)]",
                  "bg-linear-to-br",
                  palette.panel,
                )}
                aria-hidden
              >
                <div
                  className="absolute inset-0 opacity-45"
                  style={{
                    backgroundImage:
                      "radial-gradient(circle at 18% 18%, rgba(255,255,255,0.28), transparent 42%), radial-gradient(circle at 82% 78%, rgba(0,0,0,0.28), transparent 48%)",
                  }}
                />
                <div className="absolute inset-0 flex flex-col justify-between p-5 text-white">
                  <div className="space-y-2">
                    {meta ? (
                      <p
                        className={cn(
                          "text-[0.7rem] font-semibold tracking-[0.14em] uppercase",
                          palette.accent,
                        )}
                      >
                        {meta}
                      </p>
                    ) : null}
                    <p className="text-2xl font-bold leading-tight tracking-tight">
                      {skill.name}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-8">
              <header className="space-y-3">
                <p className="text-xs font-semibold tracking-[0.16em] text-brand-blue/70 uppercase">
                  Skill area
                </p>
                <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl">
                  {skill.name}
                </h1>
                <p className="text-sm text-muted-foreground sm:text-base">
                  {cycle.name}
                  {cycle.window?.closesAt
                    ? ` · Registration closes ${formatCompetitionDate(cycle.window.closesAt)}`
                    : null}
                </p>
                {meta ? (
                  <p className="text-sm font-medium text-foreground/80">{meta}</p>
                ) : null}
              </header>

              <section className="space-y-3" aria-labelledby="about-skill-heading">
                <h2
                  id="about-skill-heading"
                  className="text-lg font-semibold tracking-tight text-foreground"
                >
                  About this skill area
                </h2>
                {about ? (
                  <p className="max-w-2xl text-base leading-relaxed text-foreground/90 whitespace-pre-wrap">
                    {about}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Details for this skill area will appear here when published.
                  </p>
                )}
              </section>

              <SkillSponsorsStrip sponsors={skill.sponsors ?? []} />

              <section
                className="space-y-4 rounded-2xl bg-card p-5 ring-1 ring-border sm:p-6"
                aria-labelledby="criteria-heading"
              >
                <div className="space-y-1">
                  <h2
                    id="criteria-heading"
                    className="text-lg font-semibold tracking-tight text-foreground"
                  >
                    Criteria documents
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Download official criteria before you register. General
                    criteria apply to the whole competition; skill-area criteria
                    apply to {skill.name} only.
                  </p>
                </div>
                {cycle?.hasGeneralCriteriaDocument ||
                skill.hasCriteriaDocument ? (
                  <div className="space-y-3">
                    {downloadError ? (
                      <p className="text-sm text-destructive" role="alert">
                        {downloadError}
                      </p>
                    ) : null}
                    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                      {cycle?.hasGeneralCriteriaDocument ? (
                        <Button
                          type="button"
                          variant="outline"
                          className="min-h-11 gap-2"
                          disabled={downloadPending !== null}
                          onClick={() => void onDownloadGeneralCriteria()}
                          data-testid="download-general-criteria"
                        >
                          <DownloadIcon className="size-4" aria-hidden />
                          {downloadPending === "general"
                            ? "Downloading…"
                            : "Download general criteria"}
                        </Button>
                      ) : null}
                      {skill.hasCriteriaDocument ? (
                        <Button
                          type="button"
                          variant="outline"
                          className="min-h-11 gap-2"
                          disabled={downloadPending !== null}
                          onClick={() => void onDownloadSkillCriteria()}
                          data-testid={`download-criteria-${skill.skillId}`}
                        >
                          <DownloadIcon className="size-4" aria-hidden />
                          {downloadPending === "skill"
                            ? "Downloading…"
                            : "Download skill-area criteria"}
                        </Button>
                      ) : null}
                    </div>
                    {(cycle?.generalCriteriaFileName ||
                      skill.criteriaFileName) && (
                      <ul className="space-y-1 text-xs text-muted-foreground">
                        {cycle?.generalCriteriaFileName ? (
                          <li>
                            General: {cycle.generalCriteriaFileName}
                          </li>
                        ) : null}
                        {skill.criteriaFileName ? (
                          <li>Skill area: {skill.criteriaFileName}</li>
                        ) : null}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No criteria documents have been published for this
                    competition or skill area yet.
                  </p>
                )}
              </section>

              <section
                className="space-y-4 rounded-2xl bg-card p-5 ring-1 ring-border sm:p-6"
                aria-labelledby="register-heading"
              >
                <div className="space-y-1">
                  <h2
                    id="register-heading"
                    className="text-lg font-semibold tracking-tight text-foreground"
                  >
                    Ready to compete?
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {alreadyRegistered
                      ? `Open your competitor dashboard for ${skill.name}.`
                      : status === "authenticated" &&
                          isCompetitorRole(me?.role ?? "")
                        ? `Continue registration for ${skill.name}.`
                        : `Create a competitor account to register for ${skill.name}.`}
                  </p>
                </div>
                <Button
                  size="lg"
                  className="min-h-11 w-full gap-2 sm:w-auto"
                  asChild
                  data-testid="start-registration"
                >
                  <Link href={startRegistrationHref}>
                    {startRegistrationLabel}
                    <ArrowRightIcon className="size-4 opacity-80" aria-hidden />
                  </Link>
                </Button>
              </section>

              {cycle.skills.length > 1 ? (
                <p className="text-sm text-muted-foreground">
                  Looking for another skill?{" "}
                  <Link
                    href={`/competitions/${competitionId}/skills`}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    Browse all skill areas
                  </Link>
                  {cycle.skills
                    .filter((s) => s.skillId !== skill.skillId)
                    .slice(0, 3)
                    .map((s) => (
                      <span key={s.skillId}>
                        {" · "}
                        <Link
                          href={skillDetailHref(competitionId, s.skillId)}
                          className="font-medium text-primary underline-offset-4 hover:underline"
                        >
                          {s.name}
                        </Link>
                      </span>
                    ))}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
