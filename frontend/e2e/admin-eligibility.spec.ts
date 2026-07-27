import { test, expect, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const COMPETITOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

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

function isScreenUrl(url: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/admin/")) return false;
  return pathname.includes(`/competitors/${COMPETITOR_ID}:screen`);
}

function isOverrideUrl(url: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/admin/")) return false;
  return pathname
    .replace(/\/$/, "")
    .endsWith(`/competitors/${COMPETITOR_ID}/eligibility:override`);
}

type ScreenMode = "eligible" | "ineligible" | "config";

async function mockScreen(page: Page, mode: ScreenMode): Promise<void> {
  await page.route((url) => isScreenUrl(url.toString()), async (route) => {
    if (
      route.request().resourceType() !== "fetch" &&
      route.request().resourceType() !== "xhr"
    ) {
      await route.fallback();
      return;
    }
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    if (mode === "config") {
      await fulfillJson(
        route,
        409,
        envelope("CONFIG_INCOMPLETE", "Age reference missing", [
          { name: "ageRule", reason: "CONFIG_INCOMPLETE" },
        ]),
      );
      return;
    }
    if (mode === "ineligible") {
      await fulfillJson(route, 200, {
        competitorId: COMPETITOR_ID,
        eligible: false,
        status: "INELIGIBLE",
        failedRules: ["AGE_EXCEEDS_LIMIT"],
        category: null,
        ageAtReference: 26,
      });
      return;
    }
    await fulfillJson(route, 200, {
      competitorId: COMPETITOR_ID,
      eligible: true,
      status: "ELIGIBLE",
      failedRules: [],
      category: "COMPETITIVE",
      ageAtReference: 20,
    });
  });
}

async function mockOverride(
  page: Page,
  mode: "ok" | "reason" = "ok",
): Promise<void> {
  await page.route((url) => isOverrideUrl(url.toString()), async (route) => {
    if (
      route.request().resourceType() !== "fetch" &&
      route.request().resourceType() !== "xhr"
    ) {
      await route.fallback();
      return;
    }
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const body = route.request().postDataJSON() as {
      value?: boolean;
      reason?: string;
    };
    if (mode === "reason" || !body.reason?.trim()) {
      await fulfillJson(
        route,
        422,
        envelope("REASON_REQUIRED", "Override reason is required", [
          { name: "reason", reason: "REASON_REQUIRED" },
        ]),
      );
      return;
    }
    await fulfillJson(route, 200, {
      competitorId: COMPETITOR_ID,
      eligible: Boolean(body.value),
      status: body.value ? "ELIGIBLE" : "INELIGIBLE",
      reason: body.reason,
      category: body.value ? "COMPETITIVE" : null,
    });
  });
}

async function expectNoSeriousA11y(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

const eligibilityPath = `/admin/competitions/${CYCLE_ID}/competitors/${COMPETITOR_ID}/eligibility`;

test.describe("US-ELG-01-UI eligibility screening", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-ELG-01-UI-AC1 eligible result shows may progress", async ({
    page,
  }) => {
    await mockScreen(page, "eligible");
    await page.goto(eligibilityPath);
    await expect(page.getByTestId("eligibility-screen")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByTestId("eligibility-screen").click();
    await expect(page.getByTestId("eligibility-result")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("eligibility-eligible-label")).toHaveAttribute(
      "data-eligible",
      "true",
    );
    await expect(page.getByTestId("eligibility-eligible-label")).toContainText(
      /may progress/i,
    );
  });

  test("US-ELG-01-UI-AC2 ineligible shows failing rule codes", async ({
    page,
  }) => {
    await mockScreen(page, "ineligible");
    await page.goto(eligibilityPath);
    await page.getByTestId("eligibility-screen").click();
    await expect(page.getByTestId("eligibility-eligible-label")).toHaveAttribute(
      "data-eligible",
      "false",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("eligibility-eligible-label")).toContainText(
      /INELIGIBLE/,
    );
    await expect(page.getByTestId("eligibility-failed-rules")).toContainText(
      "AGE_EXCEEDS_LIMIT",
    );
  });

  test("US-ELG-01-UI-AC3 override requires reason then applies", async ({
    page,
  }) => {
    await mockScreen(page, "ineligible");
    await mockOverride(page, "ok");
    await page.goto(eligibilityPath);
    await page.getByTestId("eligibility-screen").click();
    await expect(page.getByTestId("eligibility-result")).toBeVisible({
      timeout: 15_000,
    });

    await page.getByTestId("eligibility-override-open").click();
    await expect(page.getByTestId("eligibility-override-form")).toBeVisible();
    await page.getByTestId("override-value-eligible").check();
    await page.getByTestId("eligibility-override-continue").click();
    await expect(
      page.getByRole("alert").filter({ hasText: "REASON_REQUIRED" }).first(),
    ).toBeVisible();

    await page.getByTestId("eligibility-override-reason").fill("Borderline DOB verified");
    await page.getByTestId("eligibility-override-continue").click();
    await expect(page.getByTestId("eligibility-override-confirm")).toBeVisible();
    await page.getByTestId("eligibility-override-confirm-submit").click();

    await expect(page.getByTestId("eligibility-override-result")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("eligibility-eligible-label")).toHaveAttribute(
      "data-eligible",
      "true",
    );
  });

  test("US-ELG-01-UI-AC4 CONFIG_INCOMPLETE does not mark eligible", async ({
    page,
  }) => {
    await mockScreen(page, "config");
    await page.goto(eligibilityPath);
    await page.getByTestId("eligibility-screen").click();
    await expect(
      page.getByTestId("eligibility-config-incomplete"),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("alert").filter({ hasText: "CONFIG_INCOMPLETE" }).first(),
    ).toBeVisible();
    await expect(page.getByTestId("eligibility-eligible-label")).toHaveCount(0);
    await expect(page.getByTestId("eligibility-override-open")).toBeDisabled();
  });
});

test.describe("T242 eligibility a11y", () => {
  test("eligibility page has no critical/serious a11y violations", async ({
    page,
  }) => {
    await installAdminSession(page);
    await mockScreen(page, "ineligible");
    await page.goto(eligibilityPath);
    await expect(page.getByTestId("eligibility-screen")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByTestId("eligibility-screen").click();
    await expect(page.getByTestId("eligibility-result")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });
});
