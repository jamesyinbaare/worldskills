export const REGISTRATION_STEPS = [
  {
    id: 1,
    key: "about",
    title: "About you",
    shortTitle: "You",
    description: "Personal details and photo",
  },
  {
    id: 2,
    key: "passport",
    title: "Passport",
    shortTitle: "Passport",
    description: "Travel document details",
  },
  {
    id: 3,
    key: "school",
    title: "School & skill",
    shortTitle: "School",
    description: "School, region, and skill area",
  },
  {
    id: 4,
    key: "coach",
    title: "Coach",
    shortTitle: "Coach",
    description: "Coach or team leader",
  },
  {
    id: 5,
    key: "review",
    title: "Review & submit",
    shortTitle: "Review",
    description: "Confirm and submit",
  },
] as const;

export type RegistrationStepId = (typeof REGISTRATION_STEPS)[number]["id"];

export function clampStep(step: number): RegistrationStepId {
  if (step < 1) return 1;
  if (step > 5) return 5;
  return step as RegistrationStepId;
}
