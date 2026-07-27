"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRightIcon, DownloadIcon, FileTextIcon } from "lucide-react";
import {
  ApiError,
  downloadPublicSkillCriteriaDocument,
  triggerBrowserDownload,
  type PublicSkillOut,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type SkillAreaCardProps = {
  competitionId: string;
  skill: PublicSkillOut;
  index?: number;
};

const ACCENTS = [
  "bg-brand-blue text-brand-blue",
  "bg-brand-green text-brand-green",
  "bg-brand-magenta text-brand-magenta",
  "bg-brand-orange text-brand-orange",
] as const;

function accentFor(skillId: string, index: number) {
  let hash = index;
  for (const char of skillId) {
    hash = (hash + char.charCodeAt(0) * 13) % ACCENTS.length;
  }
  return ACCENTS[hash] ?? ACCENTS[0];
}

export function SkillAreaCard({
  competitionId,
  skill,
  index = 0,
}: SkillAreaCardProps) {
  const enterHref = `/competitions/${competitionId}/enter?skillId=${encodeURIComponent(skill.skillId)}`;
  const accent = accentFor(skill.skillId, index);
  const hasCriteria = Boolean(skill.hasCriteriaDocument);
  const meta = [
    skill.number ? `Skill ${skill.number}` : null,
    skill.familyName?.trim() || null,
  ]
    .filter(Boolean)
    .join(" · ");

  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onDownloadCriteria() {
    setPending(true);
    setError(null);
    try {
      const { blob, filename } = await downloadPublicSkillCriteriaDocument(
        competitionId,
        skill.skillId,
      );
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not download criteria document.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <article
      data-testid="skill-area-card"
      className={cn(
        "animate-comp-fade group relative overflow-hidden rounded-2xl border border-border/80 bg-card",
        "transition-[border-color,box-shadow] duration-200",
        "hover:border-brand-blue/35 hover:shadow-[0_12px_32px_-24px_rgba(0,55,100,0.45)]",
      )}
      style={{ animationDelay: `${0.05 * index}s` }}
    >
      <div
        className={cn("absolute inset-y-0 left-0 w-1", accent.split(" ")[0])}
        aria-hidden
      />

      <div className="flex flex-col gap-4 p-4 pl-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-5 sm:pl-6">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="space-y-1">
            {meta ? (
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {meta}
              </p>
            ) : null}
            <h2 className="text-lg font-bold leading-snug tracking-tight text-foreground sm:text-xl">
              {skill.name}
            </h2>
          </div>

          {hasCriteria ? (
            <p className="inline-flex max-w-full items-center gap-1.5 text-sm text-muted-foreground">
              <FileTextIcon
                className={cn("size-3.5 shrink-0", accent.split(" ")[1])}
                aria-hidden
              />
              <span className="truncate">
                {skill.criteriaFileName?.trim() || "Criteria document available"}
              </span>
            </p>
          ) : null}

          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center">
          {hasCriteria ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full gap-2 sm:w-auto"
              disabled={pending}
              onClick={() => void onDownloadCriteria()}
              data-testid={`download-criteria-${skill.skillId}`}
            >
              <DownloadIcon className="size-4" aria-hidden />
              {pending ? "Downloading…" : "Download criteria"}
            </Button>
          ) : null}
          <Button className="min-h-11 w-full gap-2 sm:min-w-36 sm:w-auto" asChild>
            <Link href={enterHref}>
              Continue
              <ArrowRightIcon className="size-4 opacity-80" aria-hidden />
            </Link>
          </Button>
        </div>
      </div>
    </article>
  );
}
