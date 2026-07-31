import { test, expect, type Page, type Route } from "@playwright/test";
import { installCompetitorSession } from "./helpers/auth";

const COMPETITOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

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

async function mockRegistrations(page: Page): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url.toString());
      return pathname.replace(/\/$/, "").endsWith("/competitors/me/registrations");
    },
    async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, [
        {
          competitorId: COMPETITOR_ID,
          competitionId: "11111111-1111-4111-8111-111111111111",
          competitionName: "National Skills 2026",
          skillId: "22222222-2222-4222-8222-222222222222",
          skillName: "Web Development",
          status: "CONSENT_PENDING",
          zoneId: null,
          consentParticipationAt: null,
        },
      ]);
    },
  );
}

async function mockConsentDownload(page: Page): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url.toString());
      return pathname
        .replace(/\/$/, "")
        .endsWith(`/competitors/${COMPETITOR_ID}/consent-form.pdf`);
    },
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition":
            'attachment; filename="guardian-consent-WSG.pdf"',
        },
        body: "%PDF-1.4 e2e",
      });
    },
  );
}

async function mockConsentUpload(page: Page): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url.toString());
      return (
        pathname
          .replace(/\/$/, "")
          .endsWith(`/competitors/${COMPETITOR_ID}/consent-form`) &&
        !pathname.endsWith(".pdf")
      );
    },
    async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, {
        competitorId: COMPETITOR_ID,
        status: "PENDING_REVIEW",
        scopesGranted: ["participation"],
        publicProfileVisible: false,
        consentFormUploadedAt: "2026-07-23T10:00:00",
        sha256: "abc123",
      });
    },
  );
}

async function mockConsentWithdraw(page: Page): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url.toString());
      return pathname
        .replace(/\/$/, "")
        .endsWith(`/competitors/${COMPETITOR_ID}/consent:withdraw`);
    },
    async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, {
        competitorId: COMPETITOR_ID,
        status: "CONSENT_PENDING",
        flags: ["CONSENT_WITHDRAWN", "CONSENT_PENDING"],
        publicProfileVisible: false,
      });
    },
  );
}

test.describe("US-REG-02-UI guardian consent", () => {
  test.beforeEach(async ({ page }) => {
    await installCompetitorSession(page);
    await mockRegistrations(page);
  });

  test("US-REG-02-UI-AC1 consent pending reminder is shown", async ({ page }) => {
    await page.goto(`/competitor/competitors/${COMPETITOR_ID}/consent`);
    await expect(page.getByTestId("consent-pending-alert")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("consent-pending-alert")).toContainText(
      "Progression is not blocked",
    );
    await expect(page.getByTestId("scope-public")).toHaveAttribute(
      "data-granted",
      "false",
    );
    await expect(page.getByTestId("consent-download")).toBeVisible();
    await expect(page.getByTestId("consent-upload-form")).toBeVisible();
  });

  test("US-REG-02-UI-AC2 upload signed PDF records participation", async ({
    page,
  }) => {
    await mockConsentDownload(page);
    await mockConsentUpload(page);
    await page.goto(`/competitor/competitors/${COMPETITOR_ID}/consent`);
    await expect(page.getByTestId("consent-upload-form")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("consent-scope-public")).not.toBeChecked();
    await page.getByTestId("consent-download").click();
    await page
      .getByTestId("consent-upload-file")
      .setInputFiles({
        name: "signed-consent.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4 e2e"),
      });
    await page.getByTestId("consent-upload-submit").click();
    await expect(page.getByTestId("consent-upload-result")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("scope-participation")).toHaveAttribute(
      "data-granted",
      "true",
    );
  });

  test("US-REG-02-UI-AC3 retired guardian link page", async ({ page }) => {
    await page.goto("/consent/e2e-old-token");
    await expect(
      page.getByRole("heading", { name: /Guardian link retired/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("consent-retired-portal-link")).toBeVisible();
  });

  test("US-REG-02-UI-AC4 withdrawal confirms and removes public display", async ({
    page,
  }) => {
    await mockConsentWithdraw(page);
    await page.goto(`/competitor/competitors/${COMPETITOR_ID}/consent`);
    await expect(page.getByTestId("consent-upload-form")).toBeVisible({
      timeout: 15_000,
    });

    await page.getByTestId("consent-withdraw").click();
    await page.getByTestId("consent-withdraw").click();
    await expect(page.getByTestId("consent-withdraw-result")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByText(/Public display is removed|not visible/i),
    ).toBeVisible();
  });
});
