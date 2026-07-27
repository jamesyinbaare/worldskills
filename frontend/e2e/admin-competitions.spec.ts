import { test, expect, type Page, type Route } from "@playwright/test";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";

type CompetitionBody = {
  competitionId: string;
  status: string;
  name: string;
  period: { start: string; end: string };
  timeZone: string;
  languages: string[];
};

function draftCycle(name = "National Skills 2026"): CompetitionBody {
  return {
    competitionId: CYCLE_ID,
    status: "DRAFT",
    name,
    period: { start: "2026-01-01", end: "2026-12-31" },
    timeZone: "Africa/Accra",
    languages: ["en"],
  };
}

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

function pathOf(requestUrl: string): string {
  return new URL(requestUrl).pathname.replace(/\/$/, "") || "/";
}

/** Ignore Next.js document navigations that share /competitions/... path shapes. */
function isApiFetch(route: Route): boolean {
  const type = route.request().resourceType();
  return type === "fetch" || type === "xhr";
}

async function mockCycleWorkspaceApis(page: Page): Promise<void> {
  await page.route(`**/competitions/${CYCLE_ID}`, async (route) => {
    if (!isApiFetch(route)) {
      await route.fallback();
      return;
    }
    if (pathOf(route.request().url()).endsWith(`/competitions/${CYCLE_ID}`) === false) {
      await route.fallback();
      return;
    }
    if (route.request().method() === "GET") {
      await fulfillJson(route, 200, draftCycle());
      return;
    }
    await route.fallback();
  });

  await page.route(`**/competitions/${CYCLE_ID}:validate`, async (route) => {
    if (!isApiFetch(route)) {
      await route.fallback();
      return;
    }
    await fulfillJson(route, 200, {
      ok: false,
      issues: [
        {
          code: "CONFIG_INCOMPLETE",
          entity: SKILL_ID,
          message: "Skill 'Web Dev' has no age rule",
          link: `/admin/competitions/${CYCLE_ID}/skills/${SKILL_ID}`,
        },
      ],
    });
  });

  await page.route(`**/competitions/${CYCLE_ID}:activate`, async (route) => {
    if (!isApiFetch(route)) {
      await route.fallback();
      return;
    }
    await fulfillJson(
      route,
      409,
      envelope("CONFIG_INCOMPLETE", "Competition configuration is incomplete", [
        { name: SKILL_ID, reason: "CONFIG_INCOMPLETE" },
      ]),
    );
  });
}

test.describe("US-CFG-01-UI / US-CFG-02-UI admin cycle workspace", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-CFG-01-UI-AC1 create form happy path lands on DRAFT workspace", async ({
    page,
  }) => {
    await page.route("**/competitions", async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      if (pathOf(route.request().url()) !== "/competitions") {
        await route.fallback();
        return;
      }
      if (route.request().method() !== "POST") {
        await fulfillJson(route, 200, []);
        return;
      }
      await fulfillJson(route, 201, draftCycle("National Skills 2026"));
    });
    await page.route(`**/competitions/${CYCLE_ID}`, async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      if (pathOf(route.request().url()).endsWith(`/competitions/${CYCLE_ID}`) === false) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, draftCycle("National Skills 2026"));
    });

    await page.goto("/admin/competitions/new");
    await expect(
      page.getByRole("heading", { name: /create competition/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.locator("#name").fill("National Skills 2026");
    await page.locator("#start").fill("2026-01-01");
    await page.locator("#end").fill("2026-12-31");
    await page.locator("#tz").fill("Africa/Accra");
    await page.getByRole("button", { name: /create draft cycle/i }).click();

    await expect(page).toHaveURL(new RegExp(`/admin/competitions/${CYCLE_ID}`), {
      timeout: 15_000,
    });
    await expect(page.getByText("DRAFT")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /National Skills 2026/i }),
    ).toBeVisible();
  });

  test("US-CFG-01-UI-AC2 field errors stay on create (BEFORE_START / COMPETITION_DUPLICATE)", async ({
    page,
  }) => {
    let postCount = 0;
    await page.route("**/competitions", async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      if (pathOf(route.request().url()) !== "/competitions") {
        await route.fallback();
        return;
      }
      if (route.request().method() !== "POST") {
        await fulfillJson(route, 200, []);
        return;
      }
      postCount += 1;
      if (postCount === 1) {
        await fulfillJson(
          route,
          422,
          envelope("VALIDATION_ERROR", "Invalid period", [
            { name: "period.end", reason: "BEFORE_START" },
          ]),
        );
        return;
      }
      await fulfillJson(
        route,
        409,
        envelope(
          "COMPETITION_DUPLICATE",
          "A competition with this name already exists in an overlapping period",
          [{ name: "name", reason: "DUPLICATE" }],
        ),
      );
    });

    await page.goto("/admin/competitions/new");
    await expect(
      page.getByRole("heading", { name: /create competition/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.locator("#name").fill("Broken Period");
    await page.locator("#start").fill("2026-06-01");
    await page.locator("#end").fill("2026-01-01");
    await page.locator("#tz").fill("Africa/Accra");
    await page.getByRole("button", { name: /create draft cycle/i }).click();

    await expect(page).toHaveURL(/\/admin\/competitions\/new/);
    await expect(page.locator("#period-end-error")).toHaveText("BEFORE_START");

    await page.locator("#start").fill("2026-01-01");
    await page.locator("#end").fill("2026-12-31");
    await page.locator("#name").fill("Duplicate Competition");
    await page.getByRole("button", { name: /create draft cycle/i }).click();

    await expect(page).toHaveURL(/\/admin\/competitions\/new/);
    await expect(
      page.getByRole("alert").filter({ hasText: "COMPETITION_DUPLICATE" }),
    ).toBeVisible();
    await expect(page.locator("#name-error")).toHaveText("DUPLICATE");
  });

  test("US-CFG-02-UI-AC1 validate lists issues with usable fix links", async ({
    page,
  }) => {
    await mockCycleWorkspaceApis(page);

    await page.goto(`/admin/competitions/${CYCLE_ID}`);
    await expect(page.getByText("DRAFT")).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /validate/i }).click();

    await expect(page.getByText("CONFIG_INCOMPLETE")).toBeVisible();
    await expect(page.getByText(/no age rule/i)).toBeVisible();

    const fixLink = page.getByRole("link", { name: /fix|corriger/i }).first();
    await expect(fixLink).toHaveAttribute(
      "href",
      `/admin/competitions/${CYCLE_ID}/skills/${SKILL_ID}`,
    );
  });

  test("US-CFG-02-UI-AC2 activate gated when validation failed", async ({
    page,
  }) => {
    await mockCycleWorkspaceApis(page);

    await page.goto(`/admin/competitions/${CYCLE_ID}`);
    await expect(page.getByText("DRAFT")).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /validate/i }).click();
    await expect(page.getByText("CONFIG_INCOMPLETE")).toBeVisible();

    const activate = page.getByRole("button", { name: /activate|activer/i });
    await expect(activate).toBeDisabled();
    await expect(page.getByText(/no age rule/i)).toBeVisible();
    await expect(page.getByText(/DRAFT/)).toBeVisible();
  });
});
