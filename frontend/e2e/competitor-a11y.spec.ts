import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installCompetitorSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const COMPETITOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

const DEFAULT_FIELDS = [
  { name: "givenNames", type: "string", required: true, maxLength: 100 },
  { name: "familyName", type: "string", required: true, maxLength: 100 },
  { name: "dateOfBirth", type: "date", required: true },
  { name: "email", type: "email", required: true },
  { name: "mobile", type: "phone", required: true },
  { name: "nationalId", type: "string", required: true },
  { name: "institutionId", type: "uuid", required: true },
  { name: "zoneId", type: "uuid", required: true },
  { name: "skillIds", type: "array", required: true },
  { name: "declarationAccepted", type: "boolean", required: true },
  { name: "photo", type: "file", required: true },
];

async function expectNoSeriousA11y(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test.describe("T233 competitor registration & consent a11y", () => {
  test("registration form has no critical/serious a11y violations", async ({
    page,
  }) => {
    await installCompetitorSession(page);
    await page.route(
      (url) => {
        const { pathname } = new URL(url.toString());
        return pathname.endsWith(
          `/competitions/${CYCLE_ID}/registration-form`,
        );
      },
      async (route) => {
        if (
          route.request().resourceType() !== "fetch" &&
          route.request().resourceType() !== "xhr"
        ) {
          await route.fallback();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            fields: DEFAULT_FIELDS,
            maxSkills: 1,
            photoMaxMb: 2,
            photoFormats: ["image/jpeg", "image/png"],
            readOnly: false,
            window: {
              opensAt: "2026-01-01T00:00:00",
              closesAt: "2026-12-31T23:59:59",
            },
          }),
        });
      },
    );

    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });

  test("consent page has no critical/serious a11y violations", async ({
    page,
  }) => {
    await installCompetitorSession(page);
    await page.route(
      (url) => {
        const { pathname } = new URL(url.toString());
        return pathname.replace(/\/$/, "").endsWith("/competitors/me/registrations");
      },
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              competitorId: COMPETITOR_ID,
              competitionId: CYCLE_ID,
              competitionName: "National Skills 2026",
              skillId: "22222222-2222-4222-8222-222222222222",
              skillName: "Web Development",
              status: "CONSENT_PENDING",
              zoneId: null,
              consentParticipationAt: null,
            },
          ]),
        });
      },
    );
    await page.goto(`/competitor/competitors/${COMPETITOR_ID}/consent`);
    await expect(page.getByTestId("consent-upload-form")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoSeriousA11y(page);
  });
});
