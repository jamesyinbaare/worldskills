import { test, expect, type Page, type Route } from "@playwright/test";
import { installInstitutionSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const INSTITUTION_ID = "99999999-9999-4999-8999-999999999999";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";
const NOMINATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

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

function isCreateNominationUrl(url: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/admin/") || pathname.includes("/institution/")) {
    return false;
  }
  return pathname
    .replace(/\/$/, "")
    .endsWith(`/competitions/${CYCLE_ID}/nominations`);
}

type CreateMode = "ok" | "limit";

async function mockCreateNomination(page: Page, mode: CreateMode): Promise<void> {
  await page.route((url) => isCreateNominationUrl(url.toString()), async (route) => {
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
    if (mode === "limit") {
      await fulfillJson(
        route,
        422,
        envelope("NOMINATION_LIMIT_REACHED", "Limit reached", [
          { name: "skillId", reason: "NOMINATION_LIMIT_REACHED" },
        ]),
      );
      return;
    }
    await fulfillJson(route, 201, {
      nominationId: NOMINATION_ID,
      status: "PENDING_REVIEW",
      competitorId: null,
      reason: null,
    });
  });
}

test.describe("US-INS-01-UI institution nominations", () => {
  test.beforeEach(async ({ page }) => {
    await installInstitutionSession(page);
  });

  test("US-INS-01-UI-AC1 nominate within limit shows PENDING_REVIEW in list", async ({
    page,
  }) => {
    await mockCreateNomination(page, "ok");
    await page.goto(`/institution/competitions/${CYCLE_ID}/nominations/new`);
    await expect(page.getByTestId("nomination-form")).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("#institutionId").fill(INSTITUTION_ID);
    await page.locator("#skillId").fill(SKILL_ID);
    await page.locator("#competitorRef").fill("comp-ref-01");
    await page.getByTestId("nomination-submit").click();

    await expect(page).toHaveURL(
      new RegExp(`/institution/competitions/${CYCLE_ID}/nominations$`),
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("nomination-list")).toBeVisible();
    const row = page.getByTestId("nomination-row").first();
    await expect(row).toHaveAttribute("data-status", "PENDING_REVIEW");
    await expect(row).toContainText("comp-ref-01");
  });

  test("US-INS-01-UI-AC2 limit exceeded keeps form without new list row", async ({
    page,
  }) => {
    await mockCreateNomination(page, "limit");
    await page.goto(`/institution/competitions/${CYCLE_ID}/nominations/new`);
    await expect(page.getByTestId("nomination-form")).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("#institutionId").fill(INSTITUTION_ID);
    await page.locator("#skillId").fill(SKILL_ID);
    await page.locator("#competitorRef").fill("comp-ref-limit");
    await page.getByTestId("nomination-submit").click();

    await expect(
      page.getByRole("alert").filter({ hasText: "NOMINATION_LIMIT_REACHED" }).first(),
    ).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/institution/competitions/${CYCLE_ID}/nominations/new`),
    );

    await page.goto(`/institution/competitions/${CYCLE_ID}/nominations`);
    await expect(
      page.getByRole("heading", { name: /nominations/i }),
    ).toBeVisible();
    await expect(page.getByTestId("nomination-row")).toHaveCount(0);
  });
});
