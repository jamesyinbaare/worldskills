import { describe, expect, it } from "vitest";
import {
  ghanaPhoneFieldError,
  isValidGhanaPhone,
  requiredGhanaPhoneError,
} from "./phone";

describe("isValidGhanaPhone", () => {
  it("accepts local, international, and bare forms", () => {
    expect(isValidGhanaPhone("0551234567")).toBe(true);
    expect(isValidGhanaPhone("+233551234567")).toBe(true);
    expect(isValidGhanaPhone("233551234567")).toBe(true);
    expect(isValidGhanaPhone("551234567")).toBe(true);
  });

  it("rejects incomplete and empty values", () => {
    expect(isValidGhanaPhone("")).toBe(false);
    expect(isValidGhanaPhone("055")).toBe(false);
    expect(isValidGhanaPhone("123")).toBe(false);
  });
});

describe("ghanaPhoneFieldError", () => {
  it("stays quiet while empty, errors while incomplete", () => {
    expect(ghanaPhoneFieldError("")).toBeUndefined();
    expect(ghanaPhoneFieldError("055")).toMatch(/valid Ghana mobile/i);
    expect(ghanaPhoneFieldError("0551234567")).toBeUndefined();
  });
});

describe("requiredGhanaPhoneError", () => {
  it("requires a value", () => {
    expect(requiredGhanaPhoneError("")).toMatch(/required/i);
  });
});
