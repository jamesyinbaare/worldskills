import { test, expect, type Page, type Route } from "@playwright/test";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const SKILL_A = "22222222-2222-4222-8222-222222222222";
const SKILL_B = "33333333-3333-4333-8333-333333333333";

function isApiPath(url: string, suffix: string): boolean {
  const { pathname, port, hostname } = new URL(url);
  // Next app pages run on Playwright baseURL (3100); API is on 8000.
  if (port === "3100" || pathname.includes("/_next")) {
    return false;
  }
  if (
    (hostname === "127.0.0.1" || hostname === "localhost") &&
    port !== "8000" &&
    port !== ""
  ) {
    return false;
  }
  return pathname.replace(/\/$/, "").endsWith(suffix);
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

async function mockPublicDiscovery(page: Page): Promise<void> {
  await page.route(
    (url) => isApiPath(url.toString(), "/competitions:open-for-registration"),
    async (route) => {
      if (
        route.request().resourceType() !== "fetch" &&
        route.request().resourceType() !== "xhr"
      ) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, [
        {
          competitionId: CYCLE_ID,
          name: "WorldSkills Ghana 2026",
          status: "ACTIVE",
          description:
            "National skills competition for young professionals across Ghana.",
          window: {
            opensAt: "2026-01-01T00:00:00",
            closesAt: "2026-12-31T23:59:59",
          },
        },
      ]);
    },
  );

  await page.route(
    (url) => isApiPath(url.toString(), `/competitions/${CYCLE_ID}/public`),
    async (route) => {
      if (
        route.request().resourceType() !== "fetch" &&
        route.request().resourceType() !== "xhr"
      ) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, {
        competitionId: CYCLE_ID,
        name: "WorldSkills Ghana 2026",
        description:
          "National skills competition for young professionals across Ghana.",
        period: { start: "2026-01-01", end: "2026-12-31" },
        timeZone: "Africa/Accra",
        window: {
          opensAt: "2026-01-01T00:00:00",
          closesAt: "2026-12-31T23:59:59",
        },
        skills: [
          {
            skillId: SKILL_A,
            name: "Web Development",
            number: "09",
            familyName: "Information Technology",
          },
          {
            skillId: SKILL_B,
            name: "Cloud Computing",
            number: "55",
            familyName: "Information Technology",
          },
        ],
      });
    },
  );
}

test.describe("Public competition browse", () => {
  test.beforeEach(async ({ page }) => {
    await mockPublicDiscovery(page);
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test("hero → browse cards → skills → enter preserves login next with skill", async ({
    page,
  }) => {
    await page.goto("/");
    await page
      .getByRole("main")
      .getByRole("link", { name: /browse open competitions/i })
      .first()
      .click();

    await expect(page).toHaveURL(/\/competitions\/?$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /open competitions/i }),
    ).toBeVisible();
    await expect(page.getByTestId("competition-card").first()).toContainText(
      "WorldSkills Ghana 2026",
    );

    await page.getByTestId("competition-card").first().click();
    await expect(page).toHaveURL(new RegExp(`/competitions/${CYCLE_ID}/skills`));
    await expect(
      page.getByRole("heading", { level: 1, name: /WorldSkills Ghana 2026/i }),
    ).toBeVisible();
    await expect(page.getByTestId("skill-area-card")).toHaveCount(2);

    await page
      .getByTestId("skill-area-card")
      .first()
      .getByRole("link", { name: /continue/i })
      .click();
    await expect(page).toHaveURL(
      new RegExp(`/competitions/${CYCLE_ID}/enter\\?skillId=${SKILL_A}`),
    );
    await expect(page.getByText(/Selected skill area/i)).toBeVisible();
    await expect(page.getByText(/Web Development/)).toBeVisible();

    await page.getByTestId("register-as-competitor").click();
    await expect(page).toHaveURL(/\/login/);
    const url = new URL(page.url());
    expect(url.searchParams.get("next")).toBe(
      `/competitor/competitions/${CYCLE_ID}/register?skillId=${SKILL_A}`,
    );

    await page.goto(
      `/competitions/${CYCLE_ID}/enter?skillId=${encodeURIComponent(SKILL_B)}`,
    );
    await page.getByTestId("register-as-institution").click();
    await expect(page).toHaveURL(/\/login/);
    const instUrl = new URL(page.url());
    expect(instUrl.searchParams.get("next")).toBe(
      `/institution/competitions/${CYCLE_ID}/register?skillId=${SKILL_B}`,
    );
  });
});
