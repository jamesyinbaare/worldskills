"use client";

import Link from "next/link";
import { FileTextIcon } from "lucide-react";
import type { PublicSkillOut } from "@/lib/api";
import {
  skillCoverPalette,
  skillDetailHref,
} from "@/components/competitions/SkillAreasCarousel";
import { cn } from "@/lib/utils";

type SkillAreaCardProps = {
  competitionId: string;
  skill: PublicSkillOut;
  index?: number;
};

export function SkillAreaCard({
  competitionId,
  skill,
  index = 0,
}: SkillAreaCardProps) {
  const href = skillDetailHref(competitionId, skill.skillId);
  const palette = skillCoverPalette(skill.skillId, index);
  const hasCriteria = Boolean(skill.hasCriteriaDocument);
  const meta = [
    skill.number ? `Skill ${skill.number}` : null,
    skill.familyName?.trim() || null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      href={href}
      data-testid="skill-area-card"
      aria-label={`${skill.name} — view skill area details`}
      className={cn(
        "animate-comp-fade group flex h-full flex-col overflow-hidden rounded-2xl",
        "border border-border/70 bg-card shadow-[0_14px_36px_-28px_rgba(0,55,100,0.45)]",
        "outline-none transition-[transform,box-shadow,border-color] duration-300 ease-out",
        "hover:-translate-y-1 hover:border-brand-blue/30 hover:shadow-[0_24px_44px_-24px_rgba(0,55,100,0.55)]",
        "focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2",
      )}
      style={{ animationDelay: `${0.04 * index}s` }}
    >
      <div
        className={cn(
          "relative aspect-16/10 overflow-hidden bg-linear-to-br sm:aspect-4/3",
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
        <div
          className={cn(
            "absolute -top-8 right-[-8%] size-28 rounded-full blur-2xl opacity-70 transition-opacity duration-300 group-hover:opacity-100",
            palette.glow,
          )}
        />
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4 sm:p-5">
        {meta ? (
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {meta}
          </p>
        ) : null}
        <h2 className="text-lg font-bold leading-snug tracking-tight text-foreground sm:text-xl">
          {skill.name}
        </h2>
        {hasCriteria ? (
          <p className="mt-auto inline-flex max-w-full items-center gap-1.5 pt-1 text-sm text-muted-foreground">
            <FileTextIcon className="size-3.5 shrink-0 text-brand-blue" aria-hidden />
            <span>Criteria available</span>
          </p>
        ) : (
          <p className="mt-auto pt-1 text-sm text-muted-foreground/80">
            View details
          </p>
        )}
      </div>
    </Link>
  );
}
