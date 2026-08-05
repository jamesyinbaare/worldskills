"use client";

import { BadgeCheck, CalendarCheck, Check, Sparkles } from "lucide-react";

import {
  formatIsoDateLong,
  type AgeEligibilityCheck,
} from "@/lib/ageEligibility";

export type ReadyToSubmitNoticeProps = {
  checks: AgeEligibilityCheck[];
  hasCoach: boolean;
};

export function ReadyToSubmitNotice({
  checks,
  hasCoach,
}: ReadyToSubmitNoticeProps) {
  if (checks.length === 0 || checks.some((check) => !check.eligible)) {
    return null;
  }

  return (
    <div
      className="overflow-hidden rounded-2xl border border-brand-green/30 bg-brand-green/4"
      data-testid="registration-ready-to-submit"
    >
      <div className="flex items-start gap-3 border-b border-brand-green/20 bg-linear-to-r from-brand-green/14 via-brand-green/8 to-transparent px-4 py-3.5 sm:px-5">
        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-green/15 text-brand-green">
          <BadgeCheck className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 space-y-1">
          <h3 className="text-base font-semibold tracking-tight text-brand-green sm:text-lg">
            You are eligible to submit
          </h3>
          <p className="text-sm leading-relaxed text-foreground/80">
            {checks.length === 1
              ? "Your details meet the requirements for the skill area you selected."
              : "Your details meet the requirements for every skill area you selected."}
          </p>
        </div>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        {checks.map((check) => (
          <AgeCheckCard key={check.skillId} check={check} />
        ))}

        <ul className="space-y-2 pt-1">
          <ChecklistItem>Personal and affiliation details are complete.</ChecklistItem>
          <ChecklistItem>
            {hasCoach
              ? "Coach details have been added."
              : "No coach details — this section is optional."}
          </ChecklistItem>
        </ul>
      </div>

      <div className="flex items-start gap-2.5 border-t border-brand-green/20 bg-white/60 px-4 py-3.5 text-sm leading-relaxed text-muted-foreground sm:px-5">
        <Sparkles
          className="mt-0.5 size-4 shrink-0 text-brand-gold"
          aria-hidden
        />
        <p>
          Confirm the summary below, accept the declaration, then submit. Your
          competitor reference appears as soon as the registration is accepted.
        </p>
      </div>
    </div>
  );
}

function AgeCheckCard({ check }: { check: AgeEligibilityCheck }) {
  const limited = check.maxAge != null && check.age != null;

  return (
    <div className="rounded-xl border border-brand-green/20 bg-white/80 p-4">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Skill area
      </p>
      <p className="mt-0.5 text-sm font-semibold text-foreground sm:text-base">
        {check.skillName}
      </p>

      {limited ? (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric label="Your age" value={check.age} accent />
            <Metric label="Maximum allowed" value={check.maxAge} />
            <div className="col-span-2 rounded-lg border border-border/70 bg-muted/40 px-3 py-2 sm:col-span-1">
              <dt className="text-xs text-muted-foreground">Age checked on</dt>
              <dd className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                <CalendarCheck
                  className="size-3.5 shrink-0 text-muted-foreground"
                  aria-hidden
                />
                {formatIsoDateLong(check.referenceDate)}
              </dd>
            </div>
          </dl>
          <p className="mt-3 flex items-start gap-2 text-sm leading-relaxed text-foreground/90">
            <Check
              className="mt-0.5 size-4 shrink-0 text-brand-green"
              aria-hidden
            />
            <span>{withinLimitMessage(check)}</span>
          </p>
        </>
      ) : (
        <p className="mt-2 flex items-start gap-2 text-sm leading-relaxed text-foreground/90">
          <Check
            className="mt-0.5 size-4 shrink-0 text-brand-green"
            aria-hidden
          />
          <span>
            {check.openCategory
              ? "This is an open category, so no age limit applies."
              : "This skill area has no age limit."}
          </span>
        </p>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | null;
  accent?: boolean;
}) {
  return (
    <div
      className={
        accent
          ? "rounded-lg border border-brand-green/30 bg-brand-green/8 px-3 py-2"
          : "rounded-lg border border-border/70 bg-muted/40 px-3 py-2"
      }
    >
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={
          accent
            ? "text-lg font-semibold text-brand-green tabular-nums"
            : "text-lg font-semibold text-foreground tabular-nums"
        }
      >
        {value}
      </dd>
    </div>
  );
}

function ChecklistItem({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm leading-relaxed text-foreground/90">
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-brand-green/15 text-brand-green">
        <Check className="size-3" aria-hidden />
      </span>
      <span>{children}</span>
    </li>
  );
}

function withinLimitMessage(check: AgeEligibilityCheck): string {
  const age = check.age as number;
  const maxAge = check.maxAge as number;
  const spare = maxAge - age;
  if (spare === 0) {
    return `You are exactly at the age limit for ${check.skillName}, so you qualify.`;
  }
  return `You are ${spare} ${spare === 1 ? "year" : "years"} within the age limit for ${check.skillName}.`;
}
