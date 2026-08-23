"use client";

import { useEffect, useRef } from "react";
import { ApiError, type FieldError } from "@/lib/api";
import {
  fieldErrorMap as mapFieldErrors,
  humanizeErrorMessage as humanizeMessage,
  humanizeErrorTitle as humanizeTitle,
  humanizeFieldError,
  fieldLabel,
} from "@/lib/apiErrors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

export {
  humanizeFieldError,
  fieldLabel,
} from "@/lib/apiErrors";

export function humanizeErrorTitle(error: ApiError, fallback?: string): string {
  return humanizeTitle(error, fallback);
}

export function humanizeErrorMessage(error: ApiError): string {
  return humanizeMessage(error);
}

type ApiErrorAlertProps = {
  error: ApiError | null;
  title?: string;
  className?: string;
  /** Focus the alert when error appears (form submit failures). */
  autoFocus?: boolean;
};

export function ApiErrorAlert({
  error,
  title,
  className,
  autoFocus = true,
}: ApiErrorAlertProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error && autoFocus) {
      ref.current?.focus();
    }
  }, [error, autoFocus]);

  if (!error) return null;

  const heading = title ? humanizeErrorTitle(error, title) : humanizeErrorTitle(error);
  const summary = humanizeErrorMessage(error);
  const showFieldList = error.fields.length > 1;

  return (
    <Alert
      ref={ref}
      variant="destructive"
      className={cn(className)}
      tabIndex={-1}
      role="alert"
      aria-live="assertive"
    >
      <AlertTitle>{heading}</AlertTitle>
      <AlertDescription>
        <p>{summary}</p>
        {showFieldList ? (
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
            {error.fields.map((f) => (
              <li key={`${f.name}-${f.reason}`}>
                <span className="font-medium">{fieldLabel(f.name)}</span>
                {": "}
                {humanizeFieldError(f.name, f.reason)}
              </li>
            ))}
          </ul>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

/** Map envelope field errors onto a flat Record for inputs (humanized). */
export function fieldErrorMap(fields: FieldError[]): Record<string, string> {
  return mapFieldErrors(fields);
}

type FieldMessageProps = {
  id?: string;
  message?: string | null;
  className?: string;
};

export function FieldMessage({ id, message, className }: FieldMessageProps) {
  if (!message) return null;
  return (
    <p
      id={id}
      role="alert"
      className={cn("text-sm text-destructive", className)}
    >
      {message}
    </p>
  );
}
