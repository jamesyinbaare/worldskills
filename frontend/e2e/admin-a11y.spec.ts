import { test, expect, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";

async function expectNoSeriousA11y(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
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

async function mockCyclesList(page: Page): Promise<void> {
  await page.route((url) => {
    const { pathname } = new URL(url);
    if (pathname.includes("/admin/")) return false;
    return pathname.replace(/\/$/, "").endsWith("/competitions");
  }, async (route) => {
    if (
      route.request().resourceType() !== "fetch" &&
      route.request().resourceType() !== "xhr"
    ) {
      await route.fallback();
      return;
    }
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await fulfillJson(route, 200, [
      {
        competitionId: CYCLE_ID,
        status: "DRAFT",
        name: "National Skills 2026",
        period: { start: "2026-01-01", end: "2026-12-31" },
        timeZone: "Africa/Accra",
        languages: ["en"],
      },
    ]);
  });
}

async function mockSkillsList(page: Page): Promise<void> {
  await page.route((url) => {
    const { pathname } = new URL(url);
    if (pathname.includes("/admin/")) return false;
    return pathname
      .replace(/\/$/, "")
      .endsWith(`/competitions/${CYCLE_ID}/skills`);
  }, async (route) => {
    if (
      route.request().resourceType() !== "fetch" &&
      route.request().resourceType() !== "xhr"
    ) {
      await route.fallback();
      return;
    }
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await fulfillJson(route, 200, [
      {
        skillId: SKILL_ID,
        competitionId: CYCLE_ID,
        name: "Web Development",
        number: "50",
        familyId: null,
        ageRuleId: null,
        pathwayId: null,
        schemeId: null,
        capacity: 20,
        active: true,
      },
    ]);
  });
}

test.describe("T214 admin config a11y", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("cycles list has no critical/serious a11y violations", async ({
    page,
  }) => {
    await mockCyclesList(page);
    await page.goto("/admin/competitions");
    await expect(
      page.getByRole("heading", {
        name: /competitions/i,
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expectNoSeriousA11y(page);
  });

  test("skills list has no critical/serious a11y violations", async ({
    page,
  }) => {
    await mockSkillsList(page);
    await page.goto(`/admin/competitions/${CYCLE_ID}/skills`);
    await expect(
      page.getByRole("heading", { name: /skills/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expectNoSeriousA11y(page);
  });

  test("pathway editor has no critical/serious a11y violations", async ({
    page,
  }) => {
    await page.goto(
      `/admin/competitions/${CYCLE_ID}/skills/${SKILL_ID}/pathway`,
    );
    await expect(page.getByTestId("pathway-editor")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });

  test("assignments form has no critical/serious a11y violations", async ({
    page,
  }) => {
    await page.goto(`/admin/competitions/${CYCLE_ID}/assignments`);
    await expect(
      page.getByRole("heading", {
        name: /expert assignments/i,
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expectNoSeriousA11y(page);
  });
});
