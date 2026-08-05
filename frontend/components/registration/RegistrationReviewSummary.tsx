"use client";

/* eslint-disable @next/next/no-img-element -- photo preview is a local object URL */

import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RegistrationStepId } from "@/components/registration/registrationSteps";
import { cn } from "@/lib/utils";

export type ReviewItem = {
  label: string;
  value: string;
  /** Renders the value in a lighter tone — for "not provided" style entries. */
  muted?: boolean;
  wide?: boolean;
};

export type ReviewGroup = {
  title: string;
  step: RegistrationStepId;
  items: ReviewItem[];
};

export type RegistrationReviewSummaryProps = {
  name: string;
  headline: string;
  photoUrl?: string | null;
  groups: ReviewGroup[];
  onEdit?: (step: RegistrationStepId) => void;
};

export function RegistrationReviewSummary({
  name,
  headline,
  photoUrl,
  groups,
  onEdit,
}: RegistrationReviewSummaryProps) {
  return (
    <section
      className="overflow-hidden rounded-2xl border border-border/80 bg-white/90"
      data-testid="registration-review-summary"
    >
      <div className="flex items-center gap-4 border-b border-border/70 bg-linear-to-r from-brand-blue/10 via-brand-blue/4 to-transparent px-4 py-4 sm:px-5">
        {photoUrl ? (
          <img
            src={photoUrl}
            alt=""
            className="size-14 shrink-0 rounded-full border border-brand-blue/20 object-cover"
          />
        ) : (
          <span className="flex size-14 shrink-0 items-center justify-center rounded-full border border-brand-blue/20 bg-brand-blue/10 text-lg font-semibold text-brand-blue">
            {initials(name)}
          </span>
        )}
        <div className="min-w-0">
          <p className="truncate text-base font-semibold text-foreground sm:text-lg">
            {name}
          </p>
          <p className="truncate text-sm text-muted-foreground">{headline}</p>
        </div>
      </div>

      {groups.map((group) => (
        <div
          key={group.title}
          className="border-b border-border/60 px-4 py-4 last:border-b-0 sm:px-5"
        >
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              {group.title}
            </h4>
            {onEdit ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="-mr-2 h-8 gap-1.5 px-2 text-xs text-brand-blue hover:bg-brand-blue/8 hover:text-brand-blue"
                onClick={() => onEdit(group.step)}
              >
                <Pencil className="size-3.5" aria-hidden />
                Edit
                <span className="sr-only"> {group.title}</span>
              </Button>
            ) : null}
          </div>

          <dl className="mt-2 grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {group.items.map((item) => (
              <div
                key={item.label}
                className={cn("min-w-0", item.wide ? "sm:col-span-2" : null)}
              >
                <dt className="text-xs text-muted-foreground">{item.label}</dt>
                <dd
                  className={cn(
                    "text-sm wrap-break-word",
                    item.muted
                      ? "text-muted-foreground italic"
                      : "font-medium text-foreground",
                  )}
                >
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}

function initials(name: string): string {
  const parts = name
    .split(/\s+/)
    .map((p) => p.trim())
    .filter((p) => /[a-z]/i.test(p));
  if (parts.length === 0) return "—";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}
