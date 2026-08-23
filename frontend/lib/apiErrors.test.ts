import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, formatApiNetworkError } from "./api";
import { humanizeErrorMessage } from "./apiErrors";

describe("formatApiNetworkError", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns only the human fallback for fetch failures", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const msg = formatApiNetworkError(
      new TypeError("Failed to fetch"),
      "Could not load open competitions.",
    );
    expect(msg).toBe("Could not load open competitions.");
    expect(msg).not.toMatch(/Failed to fetch/i);
    expect(msg).not.toMatch(/API /);
    expect(msg).not.toMatch(/https?:\/\//);
    expect(warn).toHaveBeenCalled();
  });

  it("humanizes ApiError messages by code", () => {
    const err = new ApiError(500, {
      error: {
        code: "STORAGE_MISCONFIGURED",
        message: "GCS bucket not configured (set GCS_BUCKET_NAME)",
        fields: [],
        traceId: "t1",
      },
    });
    const msg = formatApiNetworkError(err, "Could not load open competitions.");
    expect(msg).toBe(humanizeErrorMessage(err));
    expect(msg).not.toMatch(/GCS/i);
  });
});

describe("humanizeErrorMessage", () => {
  it("prefers CODE_MESSAGES over raw infra text", () => {
    const msg = humanizeErrorMessage({
      code: "FORBIDDEN",
      message: "Missing capability: CONFIGURE_CYCLE",
      fields: [],
    });
    expect(msg).toBe("You do not have permission to do that.");
  });
});
