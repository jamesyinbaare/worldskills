/** Ghana phone: 0XXXXXXXXX, +233XXXXXXXXX / 233XXXXXXXXX, or bare 9 digits. */

export function isValidGhanaPhone(value: string): boolean {
  const digits = value.replace(/\D/g, "");
  if (!digits) return false;
  if (digits.startsWith("233")) return digits.length >= 12;
  if (digits.startsWith("0")) return digits.length === 10;
  return digits.length === 9;
}

export const GHANA_PHONE_FORMAT_HINT =
  "Enter a valid Ghana mobile number (e.g. 0551234567 or +233…).";

export const GHANA_PHONE_FIELD_HINT =
  "Ghana mobile number (e.g. 0551234567). Used for SMS alerts and password resets.";

/** Immediate field error while typing; empty input has no error yet. */
export function ghanaPhoneFieldError(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return isValidGhanaPhone(trimmed) ? undefined : GHANA_PHONE_FORMAT_HINT;
}

/** Required-field check for submit. */
export function requiredGhanaPhoneError(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Phone number is required.";
  return isValidGhanaPhone(trimmed) ? undefined : GHANA_PHONE_FORMAT_HINT;
}
