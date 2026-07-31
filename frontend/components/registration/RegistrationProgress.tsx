"use client";

import { CheckIcon } from "lucide-react";
import {
  REGISTRATION_STEPS,
  type RegistrationStepId,
} from "@/components/registration/registrationSteps";
import { cn } from "@/lib/utils";

type RegistrationProgressProps = {
  currentStep: RegistrationStepId;
  onStepSelect?: (step: RegistrationStepId) => void;
  allowJumpToCompleted?: boolean;
};

export function RegistrationProgress({
  currentStep,
  onStepSelect,
  allowJumpToCompleted = true,
}: RegistrationProgressProps) {
  const progressPct = ((currentStep - 1) / (REGISTRATION_STEPS.length - 1)) * 100;

  return (
    <nav
      aria-label="Registration progress"
      className="animate-comp-fade rounded-2xl border border-border/70 bg-white/80 p-4 shadow-[0_12px_40px_-28px_rgba(0,55,100,0.45)] backdrop-blur-sm sm:p-5"
      data-testid="registration-progress"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-brand-blue/70 uppercase">
          Step {currentStep} of {REGISTRATION_STEPS.length}
        </p>
        <p className="text-sm font-semibold text-primary">
          {REGISTRATION_STEPS[currentStep - 1]?.title}
        </p>
      </div>

      <div className="relative mb-5 hidden h-1.5 overflow-hidden rounded-full bg-[#003764]/10 sm:block">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-linear-to-r from-[#003764] via-[#00853f] to-[#ffcc00] transition-[width] duration-500 ease-out"
          style={{ width: `${progressPct}%` }}
          aria-hidden
        />
      </div>

      <ol className="grid grid-cols-5 gap-1 sm:gap-2">
        {REGISTRATION_STEPS.map((step) => {
          const done = step.id < currentStep;
          const active = step.id === currentStep;
          const clickable =
            allowJumpToCompleted && onStepSelect && step.id <= currentStep;
          return (
            <li key={step.id} className="min-w-0">
              <button
                type="button"
                disabled={!clickable}
                aria-current={active ? "step" : undefined}
                onClick={() => clickable && onStepSelect?.(step.id)}
                className={cn(
                  "flex w-full flex-col items-center gap-1.5 rounded-xl px-0.5 py-1 text-center transition-colors",
                  clickable && "hover:bg-muted/60",
                  !clickable && "cursor-default",
                )}
              >
                <span
                  className={cn(
                    "flex size-8 items-center justify-center rounded-full border text-xs font-bold transition-colors sm:size-9 sm:text-sm",
                    done &&
                      "border-[#00853f] bg-[#00853f] text-white",
                    active &&
                      "border-[#003764] bg-[#003764] text-white shadow-[0_8px_20px_-10px_rgba(0,55,100,0.8)]",
                    !done &&
                      !active &&
                      "border-[#003764]/20 bg-white text-[#003764]/45",
                  )}
                >
                  {done ? <CheckIcon className="size-4" aria-hidden /> : step.id}
                </span>
                <span
                  className={cn(
                    "hidden truncate text-[0.65rem] font-semibold tracking-tight sm:block sm:text-xs",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {step.shortTitle}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
