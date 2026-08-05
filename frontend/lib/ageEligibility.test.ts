import { describe, expect, it } from "vitest";
import {
  computeAge,
  findAgeIneligibilities,
  formatIsoDateLong,
  summarizeAgeEligibility,
} from "./ageEligibility";

describe("computeAge", () => {
  it("counts full years before the reference date", () => {
    expect(computeAge("2000-01-15", "2026-01-01")).toBe(25);
    expect(computeAge("2000-01-15", "2026-01-15")).toBe(26);
  });
});

describe("findAgeIneligibilities", () => {
  const skill = {
    skillId: "skill-1",
    name: "Plumbing",
    maxAge: 23,
    referenceDate: "2026-01-01",
    openCategoryEnabled: false,
  };

  it("returns a clear reason when age exceeds max", () => {
    const hits = findAgeIneligibilities("1999-06-01", ["skill-1"], [skill]);
    expect(hits).toHaveLength(1);
    expect(hits[0].age).toBe(26);
    expect(hits[0].maxAge).toBe(23);
    expect(hits[0].message).toContain("Plumbing");
    expect(hits[0].message).toContain("26");
    expect(hits[0].message).toContain("23");
    expect(hits[0].message).toContain(formatIsoDateLong("2026-01-01"));
    expect(hits[0].message).toMatch(/not eligible/i);
  });

  it("allows age equal to maxAge", () => {
    expect(
      findAgeIneligibilities("2003-01-01", ["skill-1"], [skill]),
    ).toHaveLength(0);
  });

  it("does not block when open category is enabled", () => {
    expect(
      findAgeIneligibilities("1990-01-01", ["skill-1"], [
        { ...skill, openCategoryEnabled: true },
      ]),
    ).toHaveLength(0);
  });
});

describe("summarizeAgeEligibility", () => {
  const skill = {
    skillId: "skill-1",
    name: "Plumbing",
    maxAge: 23,
    referenceDate: "2026-01-01",
    openCategoryEnabled: false,
  };

  it("reports a passing check with the age and limit used", () => {
    const [check] = summarizeAgeEligibility("2005-06-01", ["skill-1"], [skill]);
    expect(check.eligible).toBe(true);
    expect(check.age).toBe(20);
    expect(check.maxAge).toBe(23);
    expect(check.referenceDate).toBe("2026-01-01");
  });

  it("drops the limit for open categories and skills without a max age", () => {
    const open = summarizeAgeEligibility("1990-01-01", ["skill-1"], [
      { ...skill, openCategoryEnabled: true },
    ]);
    expect(open[0]).toMatchObject({ maxAge: null, eligible: true });

    const uncapped = summarizeAgeEligibility("1990-01-01", ["skill-1"], [
      { ...skill, maxAge: null },
    ]);
    expect(uncapped[0]).toMatchObject({ maxAge: null, eligible: true });
  });

  it("skips unknown skills and treats a missing date of birth as eligible", () => {
    expect(summarizeAgeEligibility("2005-06-01", ["other"], [skill])).toEqual(
      [],
    );
    const [check] = summarizeAgeEligibility("", ["skill-1"], [skill]);
    expect(check).toMatchObject({ age: null, eligible: true });
  });
});
