import { describe, expect, it } from "vitest";
import { fieldErrorMap } from "@/components/forms/ApiErrorAlert";
import {
  canModerateScores,
  homeForRole,
  isAdminRole,
  roleMatches,
} from "@/lib/api";

describe("role helpers", () => {
  it("recognises admin roles", () => {
    expect(isAdminRole("ADMIN")).toBe(true);
    expect(isAdminRole("SUPER_ADMIN")).toBe(true);
    expect(isAdminRole("INSTITUTION")).toBe(false);
  });

  it("maps home by role", () => {
    expect(homeForRole("ADMIN")).toBe("/admin");
    expect(homeForRole("INSTITUTION")).toBe("/institution");
    expect(homeForRole("COMPETITOR")).toBe("/competitor");
  });

  it("matches required roles", () => {
    expect(roleMatches("ADMIN", "admin")).toBe(true);
    expect(roleMatches("EXPERT", "expert")).toBe(true);
    expect(roleMatches("COMPETITOR", "admin")).toBe(false);
  });

  it("gates moderate_score capability roles", () => {
    expect(canModerateScores("EXPERT")).toBe(false);
    expect(canModerateScores("CHIEF_EXPERT")).toBe(true);
    expect(canModerateScores("MODERATOR")).toBe(true);
    expect(canModerateScores("ADMIN")).toBe(true);
    expect(canModerateScores("SUPER_ADMIN")).toBe(true);
  });
});

describe("fieldErrorMap", () => {
  it("flattens envelope fields", () => {
    expect(
      fieldErrorMap([
        { name: "period.end", reason: "BEFORE_START" },
        { name: "name", reason: "REQUIRED" },
      ]),
    ).toEqual({
      "period.end": "BEFORE_START",
      name: "REQUIRED",
    });
  });
});
