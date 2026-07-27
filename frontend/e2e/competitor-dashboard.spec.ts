import { test, expect, type Page, type Route } from "@playwright/test";
import { installCompetitorSession } from "./helpers/auth";

const COMPETITION_ID = "11111111-1111-4111-8111-111111111111";
const COMPETITOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const STAGE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SKILL_ID = "22222222-2222-4222-8222-222222222222";
const SUBMISSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

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

function isApiFetch(route: Route): boolean {
  const type = route.request().resourceType();
  return type === "fetch" || type === "xhr";
}

function apiPath(url: string, suffix: string): boolean {
  const { pathname } = new URL(url);
  // App routes under /competitor — do not confuse with API /competitors/...
  if (
    pathname === "/competitor" ||
    pathname.startsWith("/competitor/") ||
    pathname.includes("/_next")
  ) {
    return false;
  }
  return pathname.replace(/\/$/, "").endsWith(suffix);
}

async function mockEmptyRegistrations(page: Page): Promise<void> {
  await page.route(
    (url) => apiPath(url.toString(), "/competitors/me/registrations"),
    async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, []);
    },
  );
}

async function mockRegisteredPortal(page: Page): Promise<void> {
  await page.route(
    (url) => apiPath(url.toString(), "/competitors/me/registrations"),
    async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, [
        {
          competitorId: COMPETITOR_ID,
          competitionId: COMPETITION_ID,
          competitionName: "National Skills 2026",
          skillId: SKILL_ID,
          skillName: "Web Development",
          status: "REGISTERED",
          zoneId: null,
          consentParticipationAt: "2026-01-15T10:00:00",
        },
      ]);
    },
  );

  await page.route(
    (url) =>
      apiPath(url.toString(), `/competitions/${COMPETITION_ID}/me/stages`),
    async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, {
        competitionId: COMPETITION_ID,
        competitionName: "National Skills 2026",
        competitorId: COMPETITOR_ID,
        skillId: SKILL_ID,
        skillName: "Web Development",
        stages: [
          {
            stageId: STAGE_ID,
            order: 1,
            name: "Regional Project",
            type: "VIRTUAL",
            opensAt: "2026-01-01T00:00:00",
            closesAt: "2026-12-31T23:59:59",
            exerciseAvailable: true,
            exerciseTitle: "Build a responsive site",
            exerciseStatus: "PUBLISHED",
            windowStatus: "open",
            submission: {
              submissionId: null,
              state: null,
              uploadLocked: false,
              receipt: null,
            },
          },
        ],
      });
    },
  );

  await page.route(
    (url) =>
      apiPath(
        url.toString(),
        `/competitions/${COMPETITION_ID}/stages/${STAGE_ID}/exercise`,
      ),
    async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, {
        exerciseId: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        stageId: STAGE_ID,
        competitionId: COMPETITION_ID,
        title: "Build a responsive site",
        brief: "Deliver a production-ready landing page.",
        deliverables: [
          {
            code: "main",
            label: "Main package",
            required: true,
            allowedTypes: ["zip"],
            maxSizeBytes: 20_000_000,
          },
        ],
        status: "PUBLISHED",
        schemeId: null,
        latePolicy: "block",
        timedDurationSeconds: null,
        packFileName: null,
        packContentType: null,
        packScanStatus: null,
      });
    },
  );

  await page.route(
    (url) =>
      apiPath(
        url.toString(),
        `/competitions/${COMPETITION_ID}/stages/${STAGE_ID}/submissions`,
      ),
    async (route) => {
      if (!isApiFetch(route)) {
        await route.fallback();
        return;
      }
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 201, {
        submissionId: SUBMISSION_ID,
        competitionId: COMPETITION_ID,
        stageId: STAGE_ID,
        competitorId: COMPETITOR_ID,
        state: "OPEN",
        deadlineAt: "2026-12-31T23:59:59",
        timedStartedAt: null,
        timedExpiresAt: null,
        uploadLocked: false,
        late: false,
        receipt: null,
        hash: null,
      });
    },
  );
}

test.describe("Competitor dashboard discovery", () => {
  test("unregistered competitor sees browse/register hub without sidenav", async ({
    page,
  }) => {
    await installCompetitorSession(page);
    await mockEmptyRegistrations(page);
    await page.route(
      (url) => apiPath(url.toString(), "/competitions:open-for-registration"),
      async (route) => {
        if (!isApiFetch(route)) {
          await route.fallback();
          return;
        }
        await fulfillJson(route, 200, [
          {
            competitionId: COMPETITION_ID,
            name: "Open Cup",
            status: "ACTIVE",
            description: null,
            window: {
              opensAt: "2026-01-01T00:00:00",
              closesAt: "2026-12-31T23:59:59",
            },
          },
        ]);
      },
    );

    await page.goto("/competitor");
    await expect(page.getByTestId("competitor-open-competitions")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("button", { name: "Toggle Sidebar" })).toHaveCount(
      0,
    );
    await expect(page.getByText("Open Cup")).toBeVisible();
    await expect(
      page.getByTestId(`competitor-register-${COMPETITION_ID}`),
    ).toBeVisible();
  });

  test("registered competitor reaches submit via pathway without UUID paste", async ({
    page,
  }) => {
    await installCompetitorSession(page);
    await mockRegisteredPortal(page);

    await page.goto("/competitor");
    await expect(page.getByTestId("competitor-my-competitions")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { name: "Your dashboard" })).toBeVisible();
    await expect(page.getByText("National Skills 2026").first()).toBeVisible();

    await page.getByTestId(`open-competition-${COMPETITION_ID}`).click();
    await expect(page).toHaveURL(
      new RegExp(`/competitor/competitions/${COMPETITION_ID}$`),
    );
    await expect(page.getByTestId("competitor-stage-pathway")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Build a responsive site")).toBeVisible();

    await page.getByTestId(`stage-cta-${STAGE_ID}`).click();
    await expect(page).toHaveURL(
      new RegExp(
        `/competitor/competitions/${COMPETITION_ID}/stages/${STAGE_ID}/submit`,
      ),
    );
    await expect(page.getByText("Build a responsive site")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("submission-status-message")).toBeVisible();
    await expect(page.getByTestId("portal-submit-cycle-id")).toHaveCount(0);
  });

  test("sidenav links to stages and account pages", async ({ page }) => {
    await installCompetitorSession(page);
    await mockRegisteredPortal(page);

    await page.goto("/competitor");
    await expect(page.getByRole("button", { name: "Toggle Sidebar" })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Toggle Sidebar" }).click();
    await expect(page.getByTestId("competitor-nav-stages")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("competitor-nav-dsar")).toBeVisible();
    await expect(page.getByTestId("competitor-nav-overview")).toBeVisible();

    await page.getByTestId("competitor-nav-dsar").click();
    await expect(page).toHaveURL(/\/competitor\/dsar/);
  });
});
