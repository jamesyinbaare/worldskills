"use client";

import Link from "next/link";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  FileTextIcon,
} from "lucide-react";
import type { PublicSkillOut } from "@/lib/api";
import {
  skillCoverPalette,
  skillDetailHref,
} from "@/components/competitions/SkillAreasCarousel";
import { previewText } from "@/components/competitions/format";
import { cn } from "@/lib/utils";

type SkillAreaCardProps = {
  competitionId: string;
  skill: PublicSkillOut;
  index?: number;
};

function skillMonogram(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "S";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

export function SkillAreaCard({
  competitionId,
  skill,
  index = 0,
}: SkillAreaCardProps) {
  const href = skillDetailHref(competitionId, skill.skillId);
  const palette = skillCoverPalette(skill.skillId, index);
  const hasCriteria = Boolean(skill.hasCriteriaDocument);
  const family = skill.familyName?.trim() || null;
  const number = skill.number ? `Skill ${skill.number}` : null;
  const monogram = skillMonogram(skill.name);
  const blurb = previewText(skill.description, 90);

  return (
    <Link
      href={href}
      data-testid="skill-area-card"
      aria-label={`${skill.name} — view skill area details`}
      className={cn(
        "animate-comp-fade group relative flex h-full min-h-[22rem] flex-col overflow-hidden rounded-[1.5rem] sm:min-h-[24rem]",
        "outline-none ring-offset-2",
        "shadow-[0_22px_48px_-28px_rgba(0,30,70,0.72)]",
        "transition-[transform,box-shadow] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
        "hover:-translate-y-1.5 hover:shadow-[0_32px_58px_-24px_rgba(0,30,70,0.78)]",
        "focus-visible:ring-2 focus-visible:ring-[#003764]",
      )}
      style={{ animationDelay: `${0.04 * index}s` }}
    >
      <div
        className={cn(
          "absolute inset-0 bg-linear-to-br transition-transform duration-700 ease-out group-hover:scale-[1.04]",
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
          "absolute -top-14 right-[-14%] size-48 rounded-full blur-3xl opacity-70 transition-opacity duration-500 group-hover:opacity-100",
          palette.glow,
        )}
        aria-hidden
      />

      <span
        className={cn(
          "pointer-events-none absolute inset-x-0 top-[42%] -translate-y-1/2 text-center text-[6.5rem] font-bold leading-none tracking-tight select-none",
          palette.monogram,
          "transition-transform duration-700 ease-out group-hover:scale-105",
        )}
        aria-hidden
      >
        {monogram}
      </span>

      <div className="relative flex h-full flex-1 flex-col p-5 text-white sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-2.5">
            <p
              className={cn(
                "text-[0.68rem] font-semibold tracking-[0.16em] uppercase",
                palette.accent,
              )}
            >
              {[number, family].filter(Boolean).join(" · ") || "Skill area"}
            </p>
            <h2 className="text-[1.45rem] font-bold leading-[1.12] tracking-tight sm:text-[1.6rem]">
              {skill.name}
            </h2>
            {blurb ? (
              <p className="line-clamp-2 max-w-[18rem] text-sm leading-relaxed text-white/75">
                {blurb}
              </p>
            ) : null}
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

        <div className="mt-auto space-y-4 pt-8">
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
