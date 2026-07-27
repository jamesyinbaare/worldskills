/** sessionStorage helper for post-registration confirmation payload (no PII dump in URL). */

import type { RegistrationOut } from "@/lib/api";

const PREFIX = "scms_registration_confirmation_";

export type RegistrationConfirmation = RegistrationOut;

function key(competitionId: string): string {
  return `${PREFIX}${competitionId}`;
}

export function saveRegistrationConfirmation(
  competitionId: string,
  data: RegistrationConfirmation,
): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(key(competitionId), JSON.stringify(data));
}

export function loadRegistrationConfirmation(
  competitionId: string,
): RegistrationConfirmation | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(key(competitionId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as RegistrationConfirmation;
  } catch {
    return null;
  }
}

export function clearRegistrationConfirmation(competitionId: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(key(competitionId));
}
