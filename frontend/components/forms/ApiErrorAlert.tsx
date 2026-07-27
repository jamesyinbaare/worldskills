"use client";

import { useEffect, useRef } from "react";
import { ApiError, type FieldError } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const FIELD_LABELS: Record<string, string> = {
  givenNames: "Given names",
  familyName: "Family name",
  dateOfBirth: "Date of birth",
  email: "Email",
  mobile: "Mobile",
  whatsapp: "WhatsApp",
  nationalId: "National ID",
  institutionId: "School",
  regionId: "Region",
  zoneId: "Zone",
  skillIds: "Skill",
  photo: "Photo",
  declarationAccepted: "Declaration",
  captchaToken: "Security check",
  guardianName: "Guardian name",
  guardianEmail: "Guardian email",
  guardianPhone: "Guardian phone",
  schoolCode: "School",
  code: "School code",
  window: "Registration window",
  hasPassport: "Passport",
  passportNumber: "Passport number",
  passportExpiresOn: "Passport expiry date",
};

const REASON_MESSAGES: Record<string, string> = {
  REQUIRED: "This field is required.",
  INVALID: "This value is not valid.",
  INVALID_DATE: "Enter a valid date of birth in the past.",
  DATE_FROM_DATETIME_PARSING: "Enter a valid date of birth.",
  DATE_PARSING: "Enter a valid date of birth.",
  DATE_TYPE: "Enter a valid date of birth.",
  VALUE_ERROR: "This value is not valid.",
  TYPE_ERROR: "This value is not the right type.",
  EMAIL_INVALID: "Enter a valid email address.",
  PHONE_INVALID: "Enter a valid phone number.",
  ID_INVALID: "Enter a valid national ID.",
  INVALID_CHARS: "Only letters, spaces, hyphens, and apostrophes are allowed.",
  DECLARATION_REQUIRED: "Please accept the declaration to continue.",
  PHOTO_INVALID: "Upload a valid photo within the allowed size and format.",
  SKILL_SELECTION_INVALID: "Select the required number of skills.",
  REGION_REQUIRED: "Select a region, or choose your school.",
  CONFIG_INCOMPLETE:
    "This school’s region is not mapped to a competition zone yet. Ask an admin to finish geography setup, or register with a different school/region.",
  SCHOOL_NOT_FOUND: "No school matches that search.",
  SCHOOL_INACTIVE: "That school is inactive and cannot be used.",
  WINDOW_CLOSED: "Registration is closed for this competition.",
  ABUSE_SUSPECTED: "Security check failed. Please try again.",
  FORBIDDEN: "You are not allowed to use this school.",
  DUPLICATE: "This value is already in use.",
  BEFORE_OPENS: "The end date must be after the start date.",
  PASSPORT_INVALID: "Enter a valid passport number.",
  PASSPORT_EXPIRED: "Passport expiry date must be today or in the future.",
};

const CODE_TITLES: Record<string, string> = {
  VALIDATION_ERROR: "Please check the form",
  PHOTO_INVALID: "Photo issue",
  SKILL_SELECTION_INVALID: "Skill selection",
  REGION_REQUIRED: "Region needed",
  CONFIG_INCOMPLETE: "Competition setup incomplete",
  WINDOW_CLOSED: "Registration closed",
  ABUSE_SUSPECTED: "Security check failed",
  HTTP_ERROR: "Something went wrong",
};

const CODE_MESSAGES: Record<string, string> = {
  VALIDATION_ERROR: "Some fields need attention before we can submit.",
  REQUEST_VALIDATION_FAILED: "Some fields need attention before we can submit.",
};

function fieldLabel(name: string): string {
  return FIELD_LABELS[name] ?? name.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

/** Turn API field reason codes into short user-facing copy. */
export function humanizeFieldError(name: string, reason: string): string {
  const key = reason.trim().toUpperCase();
  if (name === "dateOfBirth" && (key.includes("DATE") || key.includes("PARSING"))) {
    return "Enter a valid date of birth.";
  }
  if (REASON_MESSAGES[key]) return REASON_MESSAGES[key];
  // Fallback: soften SCREAMING_SNAKE without inventing meaning
  return reason
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}

export function humanizeErrorTitle(error: ApiError, fallback?: string): string {
  return CODE_TITLES[error.code] ?? fallback ?? "Could not complete request";
}

export function humanizeErrorMessage(error: ApiError): string {
  const trimmed = error.message?.trim() ?? "";
  if (
    !trimmed ||
    trimmed === "Request validation failed" ||
    CODE_MESSAGES[error.code]
  ) {
    if (error.fields.length === 1) {
      const f = error.fields[0];
      return `${fieldLabel(f.name)}: ${humanizeFieldError(f.name, f.reason)}`;
    }
    return CODE_MESSAGES[error.code] ?? "Some fields need attention before we can submit.";
  }
  return trimmed;
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
        {error.traceId ? (
          <details className="mt-2 text-xs opacity-90">
            <summary className="cursor-pointer">Technical details</summary>
            <p className="mt-1 break-all">
              Code: {error.code}
              {error.fields.length === 1
                ? ` · ${error.fields[0].name}: ${error.fields[0].reason}`
                : null}
              <br />
              Trace ID: {error.traceId}
            </p>
          </details>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

/** Map envelope field errors onto a flat Record for inputs (humanized). */
export function fieldErrorMap(fields: FieldError[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    out[f.name] = humanizeFieldError(f.name, f.reason);
  }
  return out;
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
