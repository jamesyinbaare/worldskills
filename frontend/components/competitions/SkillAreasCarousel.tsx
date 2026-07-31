"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FileTextIcon,
} from "lucide-react";
import type { PublicSkillOut } from "@/lib/api";
import { cn } from "@/lib/utils";

type SkillAreasCarouselProps = {
  competitionId: string;
  skills: PublicSkillOut[];
  className?: string;
  /** Optional link under the showcase (e.g. browse-all). */
  footerHref?: string;
  footerLabel?: string;
};

export const SKILL_COVER_PALETTES = [
  {
    panel: "from-[#003764] via-[#0a4f8a] to-[#00853f]",
    accent: "text-[#ffcc00]",
    glow: "bg-[#ffcc00]/30",
    wash: "from-black/5 via-transparent to-black/65",
    monogram: "text-white/12",
  },
  {
    panel: "from-[#00853f] via-[#0a6b4a] to-[#003764]",
    accent: "text-[#fee300]",
    glow: "bg-[#fee300]/25",
    wash: "from-black/5 via-transparent to-black/65",
    monogram: "text-white/12",
  },
  {
    panel: "from-[#d51067] via-[#9e0c4e] to-[#003764]",
    accent: "text-[#ffcc00]",
    glow: "bg-[#ff6c0c]/30",
    wash: "from-black/8 via-transparent to-black/70",
    monogram: "text-white/12",
  },
  {
    panel: "from-[#ff6c0c] via-[#c44f08] to-[#003764]",
    accent: "text-white",
    glow: "bg-[#fee300]/25",
    wash: "from-black/5 via-transparent to-black/65",
    monogram: "text-white/12",
  },
  {
    panel: "from-[#003764] via-[#1a4f7a] to-[#d51067]",
    accent: "text-[#ffcc00]",
    glow: "bg-[#00853f]/35",
    wash: "from-black/8 via-transparent to-black/65",
    monogram: "text-white/12",
  },
] as const;

export function skillCoverPalette(skillId: string, index: number) {
  let hash = index;
  for (const char of skillId) {
    hash = (hash + char.charCodeAt(0) * 17) % SKILL_COVER_PALETTES.length;
  }
  return SKILL_COVER_PALETTES[hash] ?? SKILL_COVER_PALETTES[0];
}

export function skillDetailHref(competitionId: string, skillId: string): string {
  return `/competitions/${competitionId}/skills/${encodeURIComponent(skillId)}`;
}

function skillMonogram(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "S";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

/** Prefer a static grid when everything fits without scrolling. */
const GRID_MAX = 4;

export function SkillAreasCarousel({
  competitionId,
  skills,
  className,
  footerHref,
  footerLabel = "Browse all skill areas",
}: SkillAreasCarouselProps) {
  if (skills.length === 0) return null;

  const useGrid = skills.length <= GRID_MAX;

  return (
    <div
      className={cn("relative", className)}
      data-testid="skill-areas-carousel"
    >
      {useGrid ? (
        <SkillAreasGrid competitionId={competitionId} skills={skills} />
      ) : (
        <SkillAreasTrack competitionId={competitionId} skills={skills} />
      )}

      {footerHref ? (
        <div className="mt-8 flex justify-center sm:mt-10">
          <Link
            href={footerHref}
            data-testid="browse-all-skill-areas"
            className={cn(
              "group inline-flex items-center gap-2 text-sm font-semibold text-primary",
              "underline-offset-4 transition-colors hover:text-brand-blue hover:underline",
            )}
          >
            {footerLabel}
            <ArrowRightIcon
              className="size-4 transition-transform duration-300 group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function SkillAreasGrid({
  competitionId,
  skills,
}: {
  competitionId: string;
  skills: PublicSkillOut[];
}) {
  const count = skills.length;
  return (
    <ul
      className={cn(
        "mx-auto grid gap-5 sm:gap-6",
        count === 1 && "max-w-md grid-cols-1",
        count === 2 && "max-w-3xl grid-cols-1 sm:grid-cols-2",
        count === 3 && "max-w-5xl grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
        count >= 4 && "max-w-6xl grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
      )}
      aria-label="Skill areas"
    >
      {skills.map((skill, index) => (
        <li key={skill.skillId} className="min-w-0">
          <SkillShowcaseCard
            competitionId={competitionId}
            skill={skill}
            index={index}
            focused
            size={count <= 2 ? "lg" : "md"}
          />
        </li>
      ))}
    </ul>
  );
}

function SkillAreasTrack({
  competitionId,
  skills,
}: {
  competitionId: string;
  skills: PublicSkillOut[];
}) {
  const trackRef = useRef<HTMLUListElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);
  const [scales, setScales] = useState<number[]>(() => skills.map(() => 1));

  const syncScrollState = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    const maxScroll = Math.max(0, el.scrollWidth - el.clientWidth);
    setCanPrev(el.scrollLeft > 8);
    setCanNext(el.scrollLeft < maxScroll - 8);

    const cards = Array.from(
      el.querySelectorAll<HTMLElement>("[data-skill-card]"),
    );
    if (cards.length === 0) return;

    const viewportCenter = el.scrollLeft + el.clientWidth / 2;
    let best = 0;
    let bestDist = Number.POSITIVE_INFINITY;
    const nextScales: number[] = [];

    cards.forEach((card, i) => {
      const center = card.offsetLeft + card.offsetWidth / 2;
      const dist = Math.abs(center - viewportCenter);
      const width = card.offsetWidth || 1;
      const t = Math.min(1, dist / (width * 1.05));
      nextScales.push(1 - t * 0.08);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    });

    setActiveIndex(best);
    setScales(nextScales);
  }, []);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    syncScrollState();
    el.addEventListener("scroll", syncScrollState, { passive: true });
    window.addEventListener("resize", syncScrollState);
    return () => {
      el.removeEventListener("scroll", syncScrollState);
      window.removeEventListener("resize", syncScrollState);
    };
  }, [skills, syncScrollState]);

  function scrollByCard(direction: -1 | 1) {
    const el = trackRef.current;
    if (!el) return;
    const card = el.querySelector<HTMLElement>("[data-skill-card]");
    const step = card ? card.offsetWidth + 24 : el.clientWidth * 0.7;
    el.scrollBy({ left: direction * step, behavior: "smooth" });
  }

  function scrollToIndex(index: number) {
    const el = trackRef.current;
    if (!el) return;
    const cards = el.querySelectorAll<HTMLElement>("[data-skill-card]");
    const card = cards[index];
    if (!card) return;
    const target = card.offsetLeft - (el.clientWidth - card.offsetWidth) / 2;
    el.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
  }

  const activeSkill = skills[activeIndex] ?? skills[0];

  return (
    <div className="relative">
      <div
        className="pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-linear-to-r from-[color-mix(in_srgb,var(--background)_92%,transparent)] to-transparent sm:w-16"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-linear-to-l from-[color-mix(in_srgb,var(--background)_92%,transparent)] to-transparent sm:w-16"
        aria-hidden
      />

      <ul
        ref={trackRef}
        className={cn(
          "flex gap-5 overflow-x-auto scroll-smooth px-4 pb-2 pt-3 sm:gap-6 sm:px-8 lg:px-10",
          "snap-x snap-mandatory",
          "scrollbar-none [-ms-overflow-style:none] [scrollbar-width:none]",
          "[&::-webkit-scrollbar]:hidden",
        )}
        aria-label="Skill areas"
      >
        {skills.map((skill, index) => {
          const scale = scales[index] ?? 1;
          const focused = index === activeIndex;
          return (
            <li
              key={skill.skillId}
              data-skill-card
              className={cn(
                "w-[min(78vw,17.5rem)] shrink-0 snap-center sm:w-[18.5rem] lg:w-[19.5rem]",
                "origin-center transition-[transform,opacity] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] will-change-transform",
              )}
              style={{
                transform: `scale(${scale}) translateZ(0)`,
                opacity: 0.7 + (scale - 0.92) * 3.75,
                zIndex: focused ? 2 : 1,
              }}
            >
              <SkillShowcaseCard
                competitionId={competitionId}
                skill={skill}
                index={index}
                focused={focused}
                size="md"
              />
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        aria-label="Previous skill areas"
        disabled={!canPrev}
        onClick={() => scrollByCard(-1)}
        className={cn(
          "absolute top-[42%] left-1 z-20 flex size-11 -translate-y-1/2 items-center justify-center rounded-full sm:left-2 sm:size-12",
          "border border-white/55 bg-[#003764]/90 text-white shadow-[0_14px_30px_-14px_rgba(0,0,0,0.55)] backdrop-blur-md",
          "transition-[opacity,transform,background-color] duration-300 ease-out",
          "hover:scale-105 hover:bg-[#003764]",
          "disabled:pointer-events-none disabled:opacity-0",
        )}
        data-testid="skill-carousel-prev"
      >
        <ChevronLeftIcon className="size-5" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Next skill areas"
        disabled={!canNext}
        onClick={() => scrollByCard(1)}
        className={cn(
          "absolute top-[42%] right-1 z-20 flex size-11 -translate-y-1/2 items-center justify-center rounded-full sm:right-2 sm:size-12",
          "border border-white/55 bg-[#003764]/90 text-white shadow-[0_14px_30px_-14px_rgba(0,0,0,0.55)] backdrop-blur-md",
          "transition-[opacity,transform,background-color] duration-300 ease-out",
          "hover:scale-105 hover:bg-[#003764]",
          "disabled:pointer-events-none disabled:opacity-0",
        )}
        data-testid="skill-carousel-next"
      >
        <ChevronRightIcon className="size-5" aria-hidden />
      </button>

      <div className="mt-6 flex flex-col items-center gap-3">
        <p
          className="animate-comp-fade text-sm font-semibold tracking-tight text-primary sm:text-base"
          key={activeSkill.skillId}
        >
          {activeSkill.name}
        </p>
        <div
          className="flex items-center justify-center gap-2"
          role="tablist"
          aria-label="Skill area pages"
        >
          {skills.map((skill, index) => {
            const active = index === activeIndex;
            return (
              <button
                key={skill.skillId}
                type="button"
                role="tab"
                aria-selected={active}
                aria-label={`Go to ${skill.name}`}
                onClick={() => scrollToIndex(index)}
                className={cn(
                  "h-2 rounded-full transition-[width,background-color,transform] duration-400 ease-out",
                  active
                    ? "w-7 bg-[#003764]"
                    : "w-2 bg-[#003764]/25 hover:bg-[#003764]/45",
                )}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SkillShowcaseCard({
  competitionId,
  skill,
  index,
  focused,
  size,
}: {
  competitionId: string;
  skill: PublicSkillOut;
  index: number;
  focused: boolean;
  size: "md" | "lg";
}) {
  const href = skillDetailHref(competitionId, skill.skillId);
  const palette = skillCoverPalette(skill.skillId, index);
  const family = skill.familyName?.trim() || null;
  const number = skill.number ? `Skill ${skill.number}` : null;
  const hasCriteria = Boolean(skill.hasCriteriaDocument);
  const monogram = skillMonogram(skill.name);

  return (
    <Link
      href={href}
      data-testid="skill-area-card"
      aria-label={`${skill.name} — view skill area details`}
      className={cn(
        "group relative block overflow-hidden rounded-[1.5rem]",
        size === "lg" ? "aspect-4/5 sm:aspect-5/6" : "aspect-3/4",
        "outline-none ring-offset-2",
        "shadow-[0_22px_48px_-28px_rgba(0,30,70,0.72)]",
        "transition-[transform,box-shadow] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
        "hover:-translate-y-1.5 hover:shadow-[0_32px_58px_-24px_rgba(0,30,70,0.78)]",
        "focus-visible:ring-2 focus-visible:ring-[#003764]",
        focused && "shadow-[0_28px_56px_-22px_rgba(0,30,70,0.8)]",
      )}
      style={{ animationDelay: `${0.05 * index}s` }}
    >
      <div
        className={cn(
          "absolute inset-0 bg-linear-to-br transition-transform duration-700 ease-out group-hover:scale-[1.05]",
          palette.panel,
        )}
        aria-hidden
      />
      <div
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage:
            "radial-gradient(circle at 18% 12%, rgba(255,255,255,0.34), transparent 38%), radial-gradient(circle at 86% 78%, rgba(0,0,0,0.32), transparent 48%)",
        }}
        aria-hidden
      />
      <div
        className={cn("absolute inset-0 bg-linear-to-b opacity-95", palette.wash)}
        aria-hidden
      />
      <div
        className={cn(
          "absolute -top-14 right-[-14%] size-48 rounded-full blur-3xl transition-opacity duration-500",
          palette.glow,
          focused ? "opacity-100" : "opacity-50 group-hover:opacity-90",
        )}
        aria-hidden
      />

      {/* Decorative monogram fills empty middle space */}
      <span
        className={cn(
          "pointer-events-none absolute inset-x-0 top-[38%] -translate-y-1/2 text-center font-bold leading-none tracking-tight select-none",
          size === "lg" ? "text-[7.5rem] sm:text-[8.5rem]" : "text-[6.5rem]",
          palette.monogram,
          "transition-transform duration-700 ease-out group-hover:scale-105",
        )}
        aria-hidden
      >
        {monogram}
      </span>

      <div className="absolute inset-0 flex flex-col p-5 text-white sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-2.5">
            {family || number ? (
              <p
                className={cn(
                  "text-[0.68rem] font-semibold tracking-[0.16em] uppercase",
                  palette.accent,
                )}
              >
                {[number, family].filter(Boolean).join(" · ")}
              </p>
            ) : (
              <p
                className={cn(
                  "text-[0.68rem] font-semibold tracking-[0.16em] uppercase",
                  palette.accent,
                )}
              >
                Skill area
              </p>
            )}
            <h3
              className={cn(
                "font-bold leading-[1.12] tracking-tight",
                size === "lg"
                  ? "text-[1.65rem] sm:text-[1.85rem]"
                  : "text-[1.45rem] sm:text-[1.6rem]",
              )}
            >
              {skill.name}
            </h3>
          </div>
          <span
            className={cn(
              "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full border border-white/35 bg-white/12",
              "transition-[transform,background-color] duration-300",
              "group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:bg-white/20",
            )}
            aria-hidden
          >
            <ArrowUpRightIcon className="size-4" />
          </span>
        </div>

        <div className="mt-auto space-y-4">
          {hasCriteria ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-2.5 py-1 text-[0.7rem] font-medium text-white/90 backdrop-blur-sm">
              <FileTextIcon className="size-3.5 shrink-0" aria-hidden />
              Criteria available
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full border border-white/20 bg-white/8 px-2.5 py-1 text-[0.7rem] font-medium text-white/75 backdrop-blur-sm">
              Open for registration
            </span>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-white/20 pt-4">
            <p className="text-sm font-semibold tracking-tight text-white">
              Explore skill area
            </p>
            <ArrowRightIcon
              className="size-4 shrink-0 text-white/85 transition-transform duration-300 group-hover:translate-x-1"
              aria-hidden
            />
          </div>
        </div>
      </div>
    </Link>
  );
}
