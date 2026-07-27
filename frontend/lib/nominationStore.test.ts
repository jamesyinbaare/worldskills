import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  loadNominations,
  saveNominations,
  upsertNomination,
} from "./nominationStore";

const CYCLE = "11111111-1111-4111-8111-111111111111";

const store = new Map<string, string>();

vi.stubGlobal("sessionStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => {
    store.set(k, v);
  },
  removeItem: (k: string) => {
    store.delete(k);
  },
  clear: () => store.clear(),
  key: () => null,
  get length() {
    return store.size;
  },
});

describe("nominationStore", () => {
  beforeEach(() => {
    store.clear();
  });

  it("returns empty when unset", () => {
    expect(loadNominations(CYCLE)).toEqual([]);
  });

  it("upserts and updates by nominationId", () => {
    upsertNomination(CYCLE, {
      nominationId: "n1",
      status: "PENDING_REVIEW",
      skillId: "s1",
      competitorRef: "ref-1",
    });
    upsertNomination(CYCLE, {
      nominationId: "n1",
      status: "APPROVED",
    });
    const rows = loadNominations(CYCLE);
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("APPROVED");
    expect(rows[0].competitorRef).toBe("ref-1");
  });

  it("round-trips via saveNominations", () => {
    saveNominations(CYCLE, [
      { nominationId: "a", status: "REJECTED", reason: "incomplete" },
    ]);
    expect(loadNominations(CYCLE)[0].reason).toBe("incomplete");
  });
});
