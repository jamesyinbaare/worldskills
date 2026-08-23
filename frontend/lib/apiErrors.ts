/** Shared API error humanization — no React, safe to import from api.ts. */

export type HumanizeErrorInput = {
  code: string;
  message: string;
  fields: { name: string; reason: string }[];
};

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
  coach: "Coach / team leader",
  "coach.surname": "Coach surname",
  "coach.firstName": "Coach first name",
  "coach.otherName": "Coach other name",
  "coach.contactNumber": "Coach phone / WhatsApp",
  "coach.email": "Coach email",
  "coach.whatsapp": "Coach phone / WhatsApp",
  "coach.dateOfBirth": "Coach date of birth",
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
  PHONE_INVALID: "Enter a valid Ghana phone number (e.g. 024XXXXXXX or +233…).",
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
  INSTITUTION_REGISTRATION_DISABLED:
    "Institution registration is currently disabled.",
  MULTIPLE_ACTIVE_NOT_ALLOWED:
    "Only one competition may be active at a time. Close the current active competition first.",
};

export const CODE_TITLES: Record<string, string> = {
  VALIDATION_ERROR: "Please check the form",
  PHOTO_INVALID: "Photo issue",
  SKILL_SELECTION_INVALID: "Skill selection",
  REGION_REQUIRED: "Region needed",
  CONFIG_INCOMPLETE: "Competition setup incomplete",
  WINDOW_CLOSED: "Registration closed",
  ABUSE_SUSPECTED: "Security check failed",
  INSTITUTION_REGISTRATION_DISABLED: "Institution registration disabled",
  MULTIPLE_ACTIVE_NOT_ALLOWED: "Another competition is already active",
  HTTP_ERROR: "Something went wrong",
  INTERNAL_ERROR: "Something went wrong",
  SERVICE_UNAVAILABLE: "Service unavailable",
  STORAGE_MISCONFIGURED: "Something went wrong",
  DATABASE_NOT_CONFIGURED: "Something went wrong",
  AUDIT_WRITE_FAILED: "Something went wrong",
  FORBIDDEN: "Not allowed",
  UNAUTHORIZED: "Sign in required",
  FILE_NOT_FOUND: "File not found",
  FILE_TYPE: "Unsupported file type",
  FILE_TOO_LARGE: "File too large",
  FILE_INFECTED: "Upload blocked",
  NOT_FOUND: "Not found",
};

export const CODE_MESSAGES: Record<string, string> = {
  VALIDATION_ERROR: "Some fields need attention before we can submit.",
  REQUEST_VALIDATION_FAILED: "Some fields need attention before we can submit.",
  INTERNAL_ERROR:
    "Something went wrong. Please try again. If it continues, contact support and share the reference ID.",
  SERVICE_UNAVAILABLE: "The service is temporarily unavailable. Please try again shortly.",
  STORAGE_MISCONFIGURED:
    "Something went wrong. Please try again. If it continues, contact support and share the reference ID.",
  DATABASE_NOT_CONFIGURED:
    "Something went wrong. Please try again. If it continues, contact support and share the reference ID.",
  AUDIT_WRITE_FAILED:
    "Something went wrong. Please try again. If it continues, contact support and share the reference ID.",
  BAD_GATEWAY:
    "Something went wrong. Please try again. If it continues, contact support and share the reference ID.",
  FORBIDDEN: "You do not have permission to do that.",
  UNAUTHORIZED: "Please sign in again.",
  FILE_NOT_FOUND: "That file could not be found.",
  FILE_TYPE: "That file type is not allowed.",
  FILE_TOO_LARGE: "That file is too large.",
  FILE_INFECTED: "That file could not be accepted. Please upload a different file.",
  CONFIG_INCOMPLETE:
    "This competition is not fully set up yet. Please contact an administrator.",
  NOT_FOUND: "We could not find what you were looking for.",
  UPLOAD_OFFSET_MISMATCH: "The upload could not continue. Please try again.",
  UPLOAD_SIZE_MISMATCH: "The upload size did not match. Please try again.",
  UPLOAD_CHUNK_SIZE: "The upload could not continue. Please try again.",
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
  if ((name === "phoneNumber" || name === "phone") && key === "DUPLICATE") {
    return "This phone number is already registered.";
  }
  if (name === "email" && key === "DUPLICATE") {
    return "This email is already registered.";
  }
  if (REASON_MESSAGES[key]) return REASON_MESSAGES[key];
  return reason
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}

export function humanizeErrorTitle(
  error: HumanizeErrorInput,
  fallback?: string,
): string {
  return CODE_TITLES[error.code] ?? fallback ?? "Could not complete request";
}

export function humanizeErrorMessage(error: HumanizeErrorInput): string {
  if (CODE_MESSAGES[error.code]) {
    if (error.fields.length === 1 && error.code === "VALIDATION_ERROR") {
      const f = error.fields[0];
      return `${fieldLabel(f.name)}: ${humanizeFieldError(f.name, f.reason)}`;
    }
    return CODE_MESSAGES[error.code];
  }

  const trimmed = error.message?.trim() ?? "";
  if (!trimmed || trimmed === "Request validation failed") {
    if (error.fields.length === 1) {
      const f = error.fields[0];
      return `${fieldLabel(f.name)}: ${humanizeFieldError(f.name, f.reason)}`;
    }
    return "Some fields need attention before we can submit.";
  }
  return trimmed;
}

export function fieldErrorMap(
  fields: { name: string; reason: string }[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    out[f.name] = humanizeFieldError(f.name, f.reason);
  }
  return out;
}

export { fieldLabel };
