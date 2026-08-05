/** Age / eligibility helpers for registration review (matches backend compute_age). */

export function computeAge(dobIso: string, onIso: string): number | null {
  const dob = parseIsoDate(dobIso);
  const on = parseIsoDate(onIso);
  if (!dob || !on) return null;
  let years = on.getUTCFullYear() - dob.getUTCFullYear();
  if (
    on.getUTCMonth() < dob.getUTCMonth() ||
    (on.getUTCMonth() === dob.getUTCMonth() &&
      on.getUTCDate() < dob.getUTCDate())
  ) {
    years -= 1;
  }
  return years;
}

export function todayIsoDate(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function formatIsoDateLong(iso: string): string {
  const parsed = parseIsoDate(iso);
  if (!parsed) return iso;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export type SkillAgeLimit = {
  skillId: string;
  name: string;
  maxAge?: number | null;
  referenceDate?: string | null;
  openCategoryEnabled?: boolean;
};

export type AgeIneligibility = {
  skillId: string;
  skillName: string;
  age: number;
  maxAge: number;
  referenceDate: string;
  message: string;
};

/** Outcome of the age check for one selected skill. */
export type AgeEligibilityCheck = {
  skillId: string;
  skillName: string;
  /** Age on the reference date, or null when the date of birth is unusable. */
  age: number | null;
  /** Null when the skill has no age limit or runs an open category. */
  maxAge: number | null;
  referenceDate: string;
  openCategory: boolean;
  eligible: boolean;
};

export function summarizeAgeEligibility(
  dateOfBirth: string | null | undefined,
  selectedSkillIds: string[],
  skills: SkillAgeLimit[],
): AgeEligibilityCheck[] {
  const dob = dateOfBirth?.trim() ?? "";

  const out: AgeEligibilityCheck[] = [];
  for (const skillId of selectedSkillIds.map((s) => s.trim()).filter(Boolean)) {
    const skill = skills.find((s) => s.skillId === skillId);
    if (!skill) continue;

    const referenceDate = skill.referenceDate?.trim() || todayIsoDate();
    const age = dob ? computeAge(dob, referenceDate) : null;
    const capped = skill.openCategoryEnabled ? null : (skill.maxAge ?? null);

    out.push({
      skillId: skill.skillId,
      skillName: skill.name,
      age,
      maxAge: capped,
      referenceDate,
      openCategory: Boolean(skill.openCategoryEnabled),
      eligible: capped == null || age == null || age <= capped,
    });
  }
  return out;
}

export function findAgeIneligibilities(
  dateOfBirth: string | null | undefined,
  selectedSkillIds: string[],
  skills: SkillAgeLimit[],
): AgeIneligibility[] {
  return summarizeAgeEligibility(dateOfBirth, selectedSkillIds, skills)
    .filter((check) => !check.eligible)
    .map((check) => {
      const age = check.age as number;
      const maxAge = check.maxAge as number;
      return {
        skillId: check.skillId,
        skillName: check.skillName,
        age,
        maxAge,
        referenceDate: check.referenceDate,
        message: `You are not eligible to register for ${check.skillName}. Your age is ${age} as of ${formatIsoDateLong(check.referenceDate)}, but this skill allows a maximum age of ${maxAge}.`,
      };
    });
}

function parseIsoDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const d = new Date(Date.UTC(y, month - 1, day));
  if (
    d.getUTCFullYear() !== y ||
    d.getUTCMonth() !== month - 1 ||
    d.getUTCDate() !== day
  ) {
    return null;
  }
  return d;
}
