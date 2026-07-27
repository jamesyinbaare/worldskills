import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function expectNoSeriousA11y(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test.describe("US-FE-00 shell smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test("US-FE-00-AC8 home has no critical/serious a11y violations", async ({
    page,
  }) => {
    await page.goto("/");
    await expectNoSeriousA11y(page);
  });

  test("US-FE-00-AC8 login has no critical/serious a11y violations", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoSeriousA11y(page);
  });

  test("US-FE-00-AC2 unauthenticated admin redirects to login", async ({
    page,
  }) => {
    await page.goto("/admin/competitions");
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });


  test("mobile menu exposes portal entry", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("main").getByRole("link", {
        name: /enter competition portal|enter portal/i,
      }),
    ).toBeVisible();
  });
});
