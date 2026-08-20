"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRightIcon,
  GraduationCapIcon,
  UsersIcon,
  WrenchIcon,
} from "lucide-react";
import {
  formatApiNetworkError,
  getPublicStats,
  type PublicStatsOut,
  type PublicStatsSkillOut,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const POLL_MS = 30_000;

function useAnimatedNumber(target: number, durationMs = 700): number {
  const [display, setDisplay] = useState(0);
  const fromRef = useRef(0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    if (from === target) {
      setDisplay(target);
      return;
    }
    const start = performance.now();
    let latest = from;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) ** 3;
      latest = Math.round(from + (target - from) * eased);
      setDisplay(latest);
      if (t < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
      fromRef.current = latest;
    };
  }, [target, durationMs]);

  return display;
}

function KpiValue({ value }: { value: number }) {
  const animated = useAnimatedNumber(value);
  return (
    <p className="mt-1 text-3xl font-bold tracking-tight text-white tabular-nums sm:text-4xl">
      {animated.toLocaleString()}
    </p>
  );
}

function SkillDetailRow({ skill }: { skill: PublicStatsSkillOut }) {
  const href = `/competitions/${skill.competitionId}/skills/${skill.skillId}`;
  const capacityLabel =
    skill.capacity != null
      ? `${skill.competitorsRegistered.toLocaleString()} / ${skill.capacity.toLocaleString()}`
      : skill.competitorsRegistered.toLocaleString();

  return (
    <li className="border-b border-border/80 last:border-b-0">
      <div className="flex items-start gap-3 py-4 sm:gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 className="text-sm font-semibold text-foreground sm:text-base">
              {skill.number ? (
                <span className="mr-2 text-brand-blue/55">{skill.number}</span>
              ) : null}
              {skill.name}
            </h3>
            <p className="shrink-0 text-right">
              <span className="text-base font-bold tabular-nums text-primary sm:text-lg">
                {capacityLabel}
              </span>
              <span className="ml-1.5 text-[0.65rem] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                registered
              </span>
            </p>
          </div>
          {skill.experts.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5">
              {skill.experts.map((expert) => (
                <li
                  key={expert.expertId}
                  className="rounded-md bg-brand-blue/6 px-2 py-0.5 text-xs font-medium text-foreground/80"
                >
                  {expert.fullName}
                </li>
              ))}
            </ul>
          ) : null}
          <Link
            href={href}
            className="inline-flex items-center gap-1 text-sm font-semibold text-brand-blue underline-offset-4 hover:underline"
          >
            View skill area
            <ArrowUpRightIcon className="size-3.5" aria-hidden />
          </Link>
        </div>
      </div>
    </li>
  );
}

export function HomeLiveStats() {
  const [stats, setStats] = useState<PublicStatsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const visibleRef = useRef(true);

  const load = useCallback(async (opts?: { soft?: boolean }) => {
    if (!opts?.soft) setLoading(true);
    try {
      const next = await getPublicStats();
      setStats(next);
      setError(null);
    } catch (err) {
      setError(formatApiNetworkError(err, "Could not load live statistics."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onVisibility = () => {
      visibleRef.current = document.visibilityState === "visible";
      if (visibleRef.current) void load({ soft: true });
    };
    document.addEventListener("visibilitychange", onVisibility);

    const poll = window.setInterval(() => {
      if (visibleRef.current) void load({ soft: true });
    }, POLL_MS);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearInterval(poll);
    };
  }, [load]);

  const sortedSkills = useMemo(() => {
    if (!stats?.skills.length) return [];
    return [...stats.skills].sort(
      (a, b) => b.competitorsRegistered - a.competitorsRegistered,
    );
  }, [stats]);

  if (!loading && !error && (!stats || stats.competitions.length === 0)) {
    return null;
  }

  const totals = stats?.totals ?? {
    competitorsRegistered: 0,
    skillAreas: 0,
    expertsAssigned: 0,
  };

  const kpis = [
    {
      key: "competitors",
      label: "Competitors registered",
      value: totals.competitorsRegistered,
      icon: UsersIcon,
    },
    {
      key: "skills",
      label: "Skill areas",
      value: totals.skillAreas,
      icon: WrenchIcon,
    },
    {
      key: "experts",
      label: "Experts assigned",
      value: totals.expertsAssigned,
      icon: GraduationCapIcon,
    },
  ] as const;

  const hasSkills = sortedSkills.length > 0;

  return (
    <div
      id="live-stats"
      aria-label="Live statistics"
      className="relative z-10 mt-auto w-full"
    >
      <div
        className="pointer-events-none absolute inset-x-0 -top-24 h-24 bg-linear-to-b from-transparent to-brand-blue/85 sm:-top-32 sm:h-32"
        aria-hidden
      />
      <div className="relative border-t border-white/15 bg-brand-blue/70 px-4 py-8 backdrop-blur-md sm:px-6 sm:py-10">
        <div className="mx-auto max-w-6xl">
          <header className="animate-hero-fade flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/65">
              Live pulse
            </p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-green/20 px-2.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-brand-highlight">
              <span className="relative flex size-1.5" aria-hidden>
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-highlight opacity-60" />
                <span className="relative inline-flex size-1.5 rounded-full bg-brand-highlight" />
              </span>
              Live
            </span>
          </header>

          {error && !stats ? (
            <p className="mt-6 text-sm text-white/70" role="status">
              {error}
            </p>
          ) : (
            <>
              <dl className="animate-hero-slide mt-6 grid gap-6 sm:grid-cols-3 sm:gap-8">
                {kpis.map((kpi) => {
                  const Icon = kpi.icon;
                  return (
                    <div
                      key={kpi.key}
                      className="relative border-l-2 border-brand-gold pl-4 sm:pl-5"
                    >
                      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/60">
                        <Icon
                          className="size-3.5 text-brand-gold/80"
                          aria-hidden
                        />
                        {kpi.label}
                      </dt>
                      <dd>
                        <KpiValue value={kpi.value} />
                      </dd>
                    </div>
                  );
                })}
              </dl>

              {hasSkills ? (
                <div className="animate-hero-fade mt-7">
                  <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
                    <SheetTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="min-h-10 border-white/35 bg-transparent text-white hover:bg-white/10 hover:text-white"
                        aria-expanded={detailsOpen}
                      >
                        View details
                      </Button>
                    </SheetTrigger>
                    <SheetContent
                      side="bottom"
                      className="max-h-[85dvh] gap-0 overflow-hidden rounded-t-2xl p-0 sm:mx-auto sm:max-w-2xl sm:border-x"
                    >
                      <SheetHeader className="border-b border-border/80 px-5 py-4 sm:px-6">
                        <SheetTitle className="text-lg font-bold tracking-tight text-primary">
                          By skill area
                        </SheetTitle>
                        <SheetDescription>
                          Registered competitors and assigned experts, ranked by
                          registration count.
                        </SheetDescription>
                      </SheetHeader>
                      <div className="overflow-y-auto px-5 sm:px-6">
                        <ul>
                          {sortedSkills.map((skill) => (
                            <SkillDetailRow
                              key={skill.skillId}
                              skill={skill}
                            />
                          ))}
                        </ul>
                      </div>
                    </SheetContent>
                  </Sheet>
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
