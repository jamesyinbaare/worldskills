import { test, expect, type Page, type Route } from "@playwright/test";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";

type SkillBody = {
  skillId: string;
  competitionId: string;
  name: string;
  number: string | null;
  familyId: string | null;
  ageRuleId: string | null;
  pathwayId: string | null;
  schemeId: string | null;
  capacity: number | null;
  active: boolean;
};

function skill(name = "Web Development"): SkillBody {
  return {
    skillId: SKILL_ID,
    competitionId: CYCLE_ID,
    name,
    number: "50",
    familyId: null,
    ageRuleId: "33333333-3333-4333-8333-333333333333",
    pathwayId: "44444444-4444-4444-8444-444444444444",
    schemeId: null,
    capacity: 20,
    active: true,
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

type CreateMode = "ok" | "required" | "capacity";

function isSkillsCollectionUrl(url: string): boolean {
  const path = new URL(url).pathname.replace(/\/$/, "");
  return path.endsWith(`/competitions/${CYCLE_ID}/skills`);
}

async function mockSkillsApis(
  page: Page,
  opts: { list?: SkillBody[]; onCreate?: CreateMode } = {},
): Promise<void> {
  const created: SkillBody[] = [...(opts.list ?? [])];
  const mode = opts.onCreate ?? "ok";

  await page.route(`**/competitions/${CYCLE_ID}/age-rules**`, async (route) => {
    if (route.request().method() === "GET") {
      await fulfillJson(route, 200, [
        {
          ageRuleId: "33333333-3333-4333-8333-333333333333",
          competitionId: CYCLE_ID,
          name: "U23",
          maxAge: 23,
          referenceDate: null,
          openCategoryEnabled: false,
        },
      ]);
      return;
    }
    await route.fallback();
  });

  await page.route(`**/competitions/${CYCLE_ID}/pathways**`, async (route) => {
    if (route.request().method() === "GET") {
      await fulfillJson(route, 200, [
        {
          pathwayId: "44444444-4444-4444-8444-444444444444",
          competitionId: CYCLE_ID,
          name: "Standard",
        },
      ]);
      return;
    }
    await route.fallback();
  });

  await page.route(`**/competitions/${CYCLE_ID}/skills**`, async (route) => {
    if (route.request().resourceType() !== "fetch" && route.request().resourceType() !== "xhr") {
      await route.fallback();
      return;
    }
    if (!isSkillsCollectionUrl(route.request().url())) {
      await route.fallback();
      return;
    }
    const method = route.request().method();
    if (method === "GET") {
      await fulfillJson(route, 200, created);
      return;
    }
    if (method === "POST") {
      if (mode === "required") {
        await fulfillJson(
          route,
          422,
          envelope("VALIDATION_ERROR", "Name is required", [
            { name: "name", reason: "REQUIRED" },
          ]),
        );
        return;
      }
      if (mode === "capacity") {
        await fulfillJson(
          route,
          422,
          envelope("VALIDATION_ERROR", "Invalid capacity", [
            { name: "capacity", reason: "INVALID_CAPACITY" },
          ]),
        );
        return;
      }
      const body = route.request().postDataJSON() as { name?: string };
      const createdSkill = skill(body.name || "Web Development");
      created.push(createdSkill);
      await fulfillJson(route, 201, createdSkill);
      return;
    }
    await route.fallback();
  });
}

test.describe("US-SKL-01-UI admin skills", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-SKL-01-UI-AC1 create skill appears in cycle skill list", async ({
    page,
  }) => {
    await mockSkillsApis(page, { list: [], onCreate: "ok" });

    await page.goto(`/admin/competitions/${CYCLE_ID}/skills/new`);
    await expect(
      page.getByRole("heading", { name: /create skill/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.locator("#name").fill("Web Development");
    await page.locator("#number").fill("50");
    await page.locator("#ageRuleId").selectOption("33333333-3333-4333-8333-333333333333");
    await page.locator("#pathwayId").selectOption("44444444-4444-4444-8444-444444444444");
    await page.locator("#capacity").fill("20");
    await page.getByRole("button", { name: /save skill/i }).click();

    await expect(page).toHaveURL(
      new RegExp(`/admin/competitions/${CYCLE_ID}/skills/?$`),
      { timeout: 15_000 },
    );
    await expect(page.getByText("Web Development")).toBeVisible();
  });

  test("US-SKL-01-UI-AC2 missing name shows REQUIRED and does not add skill", async ({
    page,
  }) => {
    await mockSkillsApis(page, { list: [], onCreate: "required" });

    await page.goto(`/admin/competitions/${CYCLE_ID}/skills/new`);
    await expect(
      page.getByRole("heading", { name: /create skill/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.locator("#name").evaluate((el: HTMLInputElement) => {
      el.removeAttribute("required");
      el.value = "   ";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.getByRole("button", { name: /save skill/i }).click();

    await expect(page).toHaveURL(
      new RegExp(`/admin/competitions/${CYCLE_ID}/skills/new`),
    );
    await expect(page.locator("#name-error")).toHaveText("REQUIRED");

    await page.goto(`/admin/competitions/${CYCLE_ID}/skills`);
    await expect(
      page.getByRole("heading", { name: /skills/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Web Development")).toHaveCount(0);
  });

  test("US-SKL-01-UI-AC2 invalid capacity shows INVALID_CAPACITY", async ({
    page,
  }) => {
    await mockSkillsApis(page, { list: [], onCreate: "capacity" });

    await page.goto(`/admin/competitions/${CYCLE_ID}/skills/new`);
    await expect(
      page.getByRole("heading", { name: /create skill/i }),
    ).toBeVisible({ timeout: 15_000 });

    await page.locator("#name").fill("Bad Capacity");
    await page.locator("#capacity").fill("0");
    await page.getByRole("button", { name: /save skill/i }).click();

    await expect(page).toHaveURL(
      new RegExp(`/admin/competitions/${CYCLE_ID}/skills/new`),
    );
    await expect(page.locator("#capacity-error")).toHaveText(
      "INVALID_CAPACITY",
    );
  });
});
