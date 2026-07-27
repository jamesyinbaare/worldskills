import { test, expect, type Page, type Route } from "@playwright/test";
import { installInstitutionSession } from "./helpers/auth";

const COMPETITION_ID = "11111111-1111-4111-8111-111111111111";
const PAST_COMPETITION_ID = "33333333-3333-4333-8333-333333333333";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";
const COMPETITOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const INSTITUTION_ID = "99999999-9999-4999-8999-999999999999";

function apiPath(url: string, suffix: string): boolean {
  try {
    const { pathname } = new URL(url);
    return pathname.replace(/\/$/, "").endsWith(suffix);
  } catch {
    return false;
  }
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

async function mockInstitutionDashboardApis(page: Page): Promise<void> {
  await page.route(
    (url) => apiPath(url.toString(), "/institutions/me/registrations"),
    async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, [
        {
          competitorId: COMPETITOR_ID,
          competitorRef: "WSG-2026-ABC12345",
          competitionId: COMPETITION_ID,
          competitionName: "National Skills 2026",
          competitionStatus: "ACTIVE",
          skillId: SKILL_ID,
          skillName: "Web Development",
          status: "PENDING_REVIEW",
          givenNames: "Ama",
          familyName: "Mensah",
          gender: "Female",
        },
      ]);
    },
  );

  await page.route(
    (url) => apiPath(url.toString(), "/institutions/me/competitions"),
    async (route) => {
      await fulfillJson(route, 200, [
        {
          competitionId: COMPETITION_ID,
          name: "National Skills 2026",
          status: "ACTIVE",
          description: "Current competition for school registration.",
          period: { start: "2026-01-01", end: "2026-12-31" },
          window: {
            opensAt: "2026-01-01T00:00:00",
            closesAt: "2026-12-31T23:59:59",
          },
        },
        {
          competitionId: PAST_COMPETITION_ID,
          name: "National Skills 2025",
          status: "CLOSED",
          description: "Previous competition cycle.",
          period: { start: "2025-01-01", end: "2025-12-31" },
          window: null,
        },
      ]);
    },
  );

  await page.route(
    (url) => apiPath(url.toString(), "/competitions:open-for-registration"),
    async (route) => {
      await fulfillJson(route, 200, [
        {
          competitionId: COMPETITION_ID,
          name: "National Skills 2026",
          status: "ACTIVE",
          window: {
            opensAt: "2026-01-01T00:00:00",
            closesAt: "2026-12-31T23:59:59",
          },
        },
      ]);
    },
  );

  await page.route(
    (url) =>
      apiPath(
        url.toString(),
        `/competitions/${COMPETITION_ID}/nomination-quotas`,
      ),
    async (route) => {
      await fulfillJson(route, 200, {
        competitionId: COMPETITION_ID,
        institutionId: INSTITUTION_ID,
        quotas: [
          {
            skillId: SKILL_ID,
            skillName: "Web Development",
            max: 3,
            used: 1,
            remaining: 2,
            configured: true,
          },
        ],
      });
    },
  );

  await page.route(
    (url) =>
      apiPath(
        url.toString(),
        `/competitions/${COMPETITION_ID}/skills:available`,
      ),
    async (route) => {
      await fulfillJson(route, 200, [
        {
          skillId: SKILL_ID,
          name: "Web Development",
          number: "17",
          familyName: null,
          active: true,
        },
      ]);
    },
  );

  await page.route(
    (url) =>
      apiPath(url.toString(), `/competitions/${COMPETITION_ID}/public`),
    async (route) => {
      await fulfillJson(route, 200, {
        competitionId: COMPETITION_ID,
        name: "National Skills 2026",
        description: null,
        period: { start: "2026-01-01", end: "2026-12-31" },
        timeZone: "Africa/Accra",
        window: null,
        skills: [
          {
            skillId: SKILL_ID,
            name: "Web Development",
            number: "17",
            familyName: null,
          },
        ],
      });
    },
  );
}

test.describe("institution dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await installInstitutionSession(page);
    await mockInstitutionDashboardApis(page);
  });

  test("shows dashboard with active competitors and filters", async ({ page }) => {
    await page.goto("/institution");
    await expect(
      page.getByRole("heading", { name: "School dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("institution-roster")).toBeVisible();
    await expect(page.getByText("Ama Mensah")).toBeVisible();
    await expect(page.getByTestId("institution-nav-competitions")).toBeVisible();
    await expect(page.getByTestId("institution-nav-nominate")).toBeVisible();
    await expect(
      page.getByTestId("institution-overview-search"),
    ).toBeVisible();
    await page.getByTestId("institution-overview-search").fill("Ama");
    await expect(
      page.getByTestId(`institution-competitor-${COMPETITOR_ID}`),
    ).toHaveAttribute("href", `/institution/competitors/${COMPETITOR_ID}/lifecycle`);
  });

  test("competitions catalog shows current and past competitions", async ({ page }) => {
    await page.goto("/institution/competitions");
    await expect(
      page.getByRole("heading", { name: "Competitions" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("institution-competitions-list")).toBeVisible();
    await expect(
      page.getByTestId(`institution-competition-${COMPETITION_ID}`),
    ).toHaveAttribute("href", `/institution/competitions/${COMPETITION_ID}`);
    await expect(
      page.getByTestId(`institution-competition-${PAST_COMPETITION_ID}`),
    ).toHaveAttribute("href", `/institution/competitions/${PAST_COMPETITION_ID}`);
  });

  test("nominate hub lists open competitions and links to skill areas", async ({
    page,
  }) => {
    await page.goto("/institution/nominate");
    await expect(
      page.getByRole("heading", { name: "Register a competitor" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("nominate-competition-list")).toBeVisible();
    await expect(
      page.getByTestId(`nominate-pick-${COMPETITION_ID}`),
    ).toHaveAttribute("href", `/institution/competitions/${COMPETITION_ID}`);
  });

  test("competition detail shows skill areas and register deep-links", async ({
    page,
  }) => {
    await page.goto(`/institution/competitions/${COMPETITION_ID}`);
    await expect(
      page.getByRole("heading", { name: "National Skills 2026" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("institution-skill-areas")).toBeVisible();
    await expect(page.getByTestId("institution-quotas")).toBeVisible();
    await expect(page.getByTestId(`quota-remaining-${SKILL_ID}`)).toHaveText(
      "2",
    );
    await expect(
      page.getByTestId(`register-skill-${SKILL_ID}`),
    ).toHaveAttribute(
      "href",
      `/institution/competitions/${COMPETITION_ID}/register?skillId=${SKILL_ID}`,
    );
    await expect(page.getByTestId("institution-competition-roster")).toContainText(
      "Ama Mensah",
    );
  });

  test("competitor link opens lifecycle details", async ({ page }) => {
    await page.goto("/institution");
    await page.getByTestId(`institution-competitor-${COMPETITOR_ID}`).click();
    await expect(
      page.getByRole("heading", { name: "Competitor lifecycle" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("National Skills 2026")).toBeVisible();
    await expect(page.getByTestId("lifecycle-competitor-ref")).toContainText(
      "WSG-2026-ABC12345",
    );
  });
});
