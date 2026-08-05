"use client";

import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  formatIsoDateLong,
  type AgeIneligibility,
} from "@/lib/ageEligibility";

export type AgeIneligibilityNoticeProps = {
  items: AgeIneligibility[];
  onChangeSkill: () => void;
  onCheckDateOfBirth: () => void;
};

export function AgeIneligibilityNotice({
  items,
  onChangeSkill,
  onCheckDateOfBirth,
}: AgeIneligibilityNoticeProps) {
  if (items.length === 0) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="overflow-hidden rounded-2xl border border-destructive/30 bg-destructive/4"
      data-testid="registration-age-ineligible"
    >
      <div className="flex items-start gap-3 border-b border-destructive/20 bg-destructive/10 px-4 py-3.5 sm:px-5">
        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
          <TriangleAlert className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 space-y-1">
          <h3 className="text-base font-semibold tracking-tight text-destructive sm:text-lg">
            You are not eligible to submit this registration
          </h3>
          <p className="text-sm leading-relaxed text-destructive/90">
            {items.length === 1
              ? "You are older than the maximum age allowed for the skill area you selected."
              : `You are older than the maximum age allowed for ${items.length} of the skill areas you selected.`}
          </p>
        </div>
      </div>

      <div className="space-y-3 px-4 py-4 sm:px-5">
        {items.map((item) => {
          const overBy = item.age - item.maxAge;
          return (
            <div
              key={item.skillId}
              className="rounded-xl border border-destructive/20 bg-white/80 p-4"
            >
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Skill area
              </p>
              <p className="mt-0.5 text-sm font-semibold text-foreground sm:text-base">
                {item.skillName}
              </p>

              <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <div className="rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2">
                  <dt className="text-xs text-muted-foreground">Your age</dt>
                  <dd className="text-lg font-semibold text-destructive tabular-nums">
                    {item.age}
                  </dd>
                </div>
                <div className="rounded-lg border border-border/70 bg-muted/40 px-3 py-2">
                  <dt className="text-xs text-muted-foreground">
                    Maximum allowed
                  </dt>
                  <dd className="text-lg font-semibold text-foreground tabular-nums">
                    {item.maxAge}
                  </dd>
                </div>
                <div className="col-span-2 rounded-lg border border-border/70 bg-muted/40 px-3 py-2 sm:col-span-1">
                  <dt className="text-xs text-muted-foreground">
                    Age checked on
                  </dt>
                  <dd className="text-sm font-medium text-foreground">
                    {formatIsoDateLong(item.referenceDate)}
                  </dd>
                </div>
              </dl>

              <p className="mt-3 text-sm leading-relaxed text-foreground/90">
                You are{" "}
                <span className="font-semibold">
                  {overBy} {overBy === 1 ? "year" : "years"}
                </span>{" "}
                above the age limit for {item.skillName}, so this registration
                cannot be accepted.
              </p>
            </div>
          );
        })}
      </div>

      <div className="space-y-3 border-t border-destructive/20 bg-white/60 px-4 py-4 sm:px-5">
        <p className="text-sm font-semibold text-foreground">What you can do</p>
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted-foreground marker:text-destructive/50">
          <li>
            Choose a different skill area with an age limit that matches your
            age.
          </li>
          <li>
            Check your date of birth if you think it was entered incorrectly.
          </li>
        </ul>
        <div className="flex flex-col gap-2 pt-1 sm:flex-row">
          <Button
            type="button"
            variant="outline"
            className="min-h-11 sm:flex-none"
            onClick={onChangeSkill}
            data-testid="age-ineligible-change-skill"
          >
            Change skill area
          </Button>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 sm:flex-none"
            onClick={onCheckDateOfBirth}
            data-testid="age-ineligible-check-dob"
          >
            Check date of birth
          </Button>
        </div>
      </div>
    </div>
  );
}
