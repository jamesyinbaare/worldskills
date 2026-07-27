import { test, expect, type Page, type Route } from "@playwright/test";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";
const SCHEME_ID = "55555555-5555-4555-8555-555555555555";
const ZONE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ZONE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

function envelope(
  code: string,
  message: string,
  fields: { name: string; reason: string }[] = [],
) {
  return {
    error: { code, message, fields, traceId: "e2e-trace" },
  };
}

async function fulfillJson(
  route: Route,
  status: number,
  body: unknown,
): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function isApiFetch(route: Route): boolean {
  const type = route.request().resourceType();
  return type === "fetch" || type === "xhr";
}

type PutMode = "ok" | "order" | "quota" | "score";

/** API pathway URL only — exclude Next.js `/admin/...` pages that share the suffix. */
function isPathwayApiUrl(url: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/admin/")) return false;
  const path = pathname.replace(/\/$/, "");
  return path.endsWith(
    `/competitions/${CYCLE_ID}/skills/${SKILL_ID}/pathway`,
  );
}

async function mockPathwayPut(page: Page, mode: PutMode): Promise<void> {
  await page.route((url) => isPathwayApiUrl(url.toString()), async (route) => {
    if (!isApiFetch(route) || route.request().method() !== "PUT") {
      await route.fallback();
      return;
    }
    if (mode === "order") {
      await fulfillJson(
        route,
        422,
        envelope("ORDER_INVALID", "Stage order must be contiguous", [
          { name: "stages.order", reason: "ORDER_INVALID" },
        ]),
      );
      return;
    }
    if (mode === "quota") {
      await fulfillJson(
        route,
        422,
        envelope("QUOTA_INVALID", "Invalid quota", [
          { name: "stages.0.quotaByZone", reason: "QUOTA_INVALID" },
        ]),
      );
      return;
    }
    if (mode === "score") {
      await fulfillJson(
        route,
        422,
        envelope("SCORE_RANGE", "Score out of range", [
          { name: "stages.0.minScore", reason: "SCORE_RANGE" },
        ]),
      );
      return;
    }
    await fulfillJson(route, 200, {
      stages: [
        {
          stageId: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          order: 1,
          type: "Regional",
          schemeId: SCHEME_ID,
          quotaByZone: { [ZONE_A]: 5, [ZONE_B]: 5 },
          minScore: 60,
          quota: 10,
        },
        {
          stageId: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          order: 2,
          type: "National",
          schemeId: SCHEME_ID,
          quotaByZone: { [ZONE_A]: 2, [ZONE_B]: 2 },
          minScore: null,
          quota: 4,
        },
      ],
      finalistsPerSkill: 4,
    });
  });
}

async function fillStage(
  page: Page,
  index: number,
  values: {
    order: string;
    type: string;
    schemeId: string;
    quotaByZone: string;
    minScore?: string;
  },
): Promise<void> {
  await page.locator(`#stage-${index}-order`).fill(values.order);
  await page.locator(`#stage-${index}-type`).fill(values.type);
  await page.locator(`#stage-${index}-schemeId`).fill(values.schemeId);
  await page.locator(`#stage-${index}-quotaByZone`).fill(values.quotaByZone);
  if (values.minScore != null) {
    await page.locator(`#stage-${index}-minScore`).fill(values.minScore);
  }
}

async function openPathwayEditor(page: Page): Promise<void> {
  await page.goto(
    `/admin/competitions/${CYCLE_ID}/skills/${SKILL_ID}/pathway`,
  );
  await expect(page.getByTestId("pathway-editor")).toBeVisible({
    timeout: 15_000,
  });
}

test.describe("US-STG-01-UI pathway editor", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-STG-01-UI-AC1 save pathway updates finalists summary", async ({
    page,
  }) => {
    await mockPathwayPut(page, "ok");
    await openPathwayEditor(page);

    await page.getByTestId("pathway-add-stage").click();

    await fillStage(page, 0, {
      order: "1",
      type: "Regional",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:5,${ZONE_B}:5`,
      minScore: "60",
    });
    await fillStage(page, 1, {
      order: "2",
      type: "National",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:2,${ZONE_B}:2`,
    });

    await page.getByTestId("pathway-save").click();

    await expect(page.getByTestId("finalists-summary")).toContainText("4", {
      timeout: 15_000,
    });
    await expect(page.locator("#stage-0-type")).toHaveValue("Regional");
  });

  test("US-STG-01-UI-AC2 ORDER_INVALID preserves unsaved local state", async ({
    page,
  }) => {
    await mockPathwayPut(page, "order");
    await openPathwayEditor(page);

    await page.getByTestId("pathway-add-stage").click();
    await fillStage(page, 0, {
      order: "1",
      type: "Keep Me",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:5`,
    });
    await fillStage(page, 1, {
      order: "3",
      type: "Skipped Order",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:2`,
    });

    await page.getByTestId("pathway-save").click();

    await expect(
      page.getByRole("alert").filter({ hasText: "ORDER_INVALID" }).first(),
    ).toBeVisible();
    await expect(page.locator("#stage-0-type")).toHaveValue("Keep Me");
    await expect(page.locator("#stage-1-order")).toHaveValue("3");
  });

  test("US-STG-01-UI-AC2 SCORE_RANGE shows error and keeps minScore", async ({
    page,
  }) => {
    await mockPathwayPut(page, "score");
    await openPathwayEditor(page);

    await fillStage(page, 0, {
      order: "1",
      type: "Regional",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:5`,
      minScore: "101",
    });
    await page.getByTestId("pathway-save").click();
    await expect(
      page.getByRole("alert").filter({ hasText: "SCORE_RANGE" }).first(),
    ).toBeVisible();
    await expect(page.locator("#stage-0-minScore")).toHaveValue("101");
  });

  test("US-STG-01-UI-AC2 QUOTA_INVALID shows error and keeps quota field", async ({
    page,
  }) => {
    await mockPathwayPut(page, "quota");
    await openPathwayEditor(page);

    await fillStage(page, 0, {
      order: "1",
      type: "Regional",
      schemeId: SCHEME_ID,
      quotaByZone: `${ZONE_A}:-1`,
    });
    await page.getByTestId("pathway-save").click();
    await expect(page.locator("#stage-0-quota-error")).toHaveText(
      "QUOTA_INVALID",
    );
    await expect(page.locator("#stage-0-quotaByZone")).toHaveValue(
      `${ZONE_A}:-1`,
    );
  });
});
