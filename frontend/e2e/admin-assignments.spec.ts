import { test, expect, type Page, type Route } from "@playwright/test";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const EXPERT_ID = "77777777-7777-4777-8777-777777777777";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";
const ZONE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const INSTITUTION_ID = "99999999-9999-4999-8999-999999999999";

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

type AssignMode = "ok" | "invalid";

/** API assignments URL only — exclude Next.js `/admin/...` pages. */
function isAssignmentsCollectionUrl(url: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/admin/")) return false;
  const path = pathname.replace(/\/$/, "");
  return path.endsWith(`/competitions/${CYCLE_ID}/assignments`);
}

async function mockAssignmentApi(page: Page, mode: AssignMode): Promise<void> {
  await page.route(
    (url) => isAssignmentsCollectionUrl(url.toString()),
    async (route) => {
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
      if (mode === "invalid") {
        await fulfillJson(
          route,
          422,
          envelope("INVALID_ASSIGNMENT", "Invalid expert or skill/zone", [
            { name: "expertId", reason: "INVALID_ASSIGNMENT" },
          ]),
        );
        return;
      }
      await fulfillJson(route, 201, {
        assignmentId: "88888888-8888-4888-8888-888888888888",
        competitionId: CYCLE_ID,
        expertId: EXPERT_ID,
        skillId: SKILL_ID,
        zoneId: ZONE_ID,
        coiFlags: [
          {
            institutionId: INSTITUTION_ID,
            reason: "SAME_INSTITUTION",
            competitorIds: [],
          },
        ],
      });
    },
  );
}

test.describe("US-SEC-01-UI expert assignment", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-SEC-01-UI-AC1 assignment shows COI flags", async ({ page }) => {
    await mockAssignmentApi(page, "ok");
    await page.goto(`/admin/competitions/${CYCLE_ID}/assignments`);
    await page.locator("#expertId").fill(EXPERT_ID);
    await page.locator("#skillId").fill(SKILL_ID);
    await page.locator("#zoneId").fill(ZONE_ID);
    await page.getByRole("button", { name: /assign expert/i }).click();
    await expect(page.getByTestId("assignment-result")).toBeVisible();
    await expect(page.getByTestId("coi-flags")).toContainText(/SAME_INSTITUTION/);
  });

  test("US-SEC-01-UI-AC2 invalid assignment shows envelope without success", async ({
    page,
  }) => {
    await mockAssignmentApi(page, "invalid");
    await page.goto(`/admin/competitions/${CYCLE_ID}/assignments`);
    await page.locator("#expertId").fill(EXPERT_ID);
    await page.locator("#skillId").fill(SKILL_ID);
    await page.locator("#zoneId").fill(ZONE_ID);
    await page.getByRole("button", { name: /assign expert/i }).click();
    await expect(page.locator("#expertId-error")).toHaveText(
      "INVALID_ASSIGNMENT",
    );
    await expect(page.getByTestId("assignment-result")).toHaveCount(0);
  });
});
