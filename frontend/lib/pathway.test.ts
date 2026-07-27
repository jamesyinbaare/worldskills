import { describe, expect, it } from "vitest";
import { parseQuotaText } from "@/lib/pathway";

describe("parseQuotaText", () => {
  it("parses zone:quota lines", () => {
    expect(
      parseQuotaText(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:10\nbbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb:5",
      ),
    ).toEqual({
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": 10,
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": 5,
    });
  });

  it("returns null for invalid lines", () => {
    expect(parseQuotaText("not-a-quota")).toBeNull();
    expect(parseQuotaText("")).toBeNull();
  });
});
