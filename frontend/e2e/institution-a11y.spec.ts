import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  installAdminSession,
  installInstitutionSession,
} from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";

async function expectNoSeriousA11y(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test.describe("T222 institution nomination a11y", () => {
  test("nomination form has no critical/serious a11y violations", async ({
    page,
  }) => {
    await installInstitutionSession(page);
    await page.goto(`/institution/competitions/${CYCLE_ID}/nominations/new`);
    await expect(page.getByTestId("nomination-form")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });

  test("admin queue has no critical/serious a11y violations", async ({
    page,
  }) => {
    await installAdminSession(page);
    await page.addInitScript(
      ({ competitionId }) => {
        sessionStorage.setItem(
          `scms_nominations_${competitionId}`,
          JSON.stringify([
            {
              nominationId: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              status: "PENDING_REVIEW",
              competitorRef: "a11y-ref",
            },
          ]),
        );
      },
      { competitionId: CYCLE_ID },
    );
    await page.goto(`/admin/competitions/${CYCLE_ID}/nominations`);
    await expect(page.getByTestId("admin-nomination-queue")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });

  test("institution home exposes nomination entry", async ({ page }) => {
    await installInstitutionSession(page);
    await page.goto("/institution");
    await expect(
      page.getByRole("heading", { name: /institution portal/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: /open nominations/i })).toBeVisible();
  });
});
