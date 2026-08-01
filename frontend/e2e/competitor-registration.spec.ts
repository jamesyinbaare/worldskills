import { test, expect, type Page, type Route } from "@playwright/test";
import path from "path";
import fs from "fs";
import os from "os";
import { installCompetitorSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const COMPETITOR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const SKILL_A = "22222222-2222-4222-8222-222222222222";
const SKILL_B = "33333333-3333-4333-8333-333333333333";
const INST_ID = "99999999-9999-4999-8999-999999999999";

const DEFAULT_FIELDS = [
  { name: "givenNames", type: "string", required: true, maxLength: 100 },
  { name: "familyName", type: "string", required: true, maxLength: 100 },
  {
    name: "gender",
    type: "enum",
    required: true,
    allowedValues: ["Male", "Female"],
  },
  { name: "dateOfBirth", type: "date", required: true },
  { name: "email", type: "email", required: true },
  { name: "mobile", type: "phone", required: true },
  { name: "whatsapp", type: "phone", required: true },
  { name: "guardianName", type: "string", required: false },
  { name: "guardianPhone", type: "phone", required: false },
  {
    name: "heardAbout",
    type: "enum",
    required: true,
    allowedValues: [
      "Social media",
      "Newspaper",
      "Friend",
      "Radio",
      "Television",
      "Website (CTVET/WorldSkills)",
      "Other means",
    ],
  },
  { name: "nationalId", type: "string", required: false },
  { name: "institutionId", type: "uuid", required: true },
  { name: "zoneId", type: "uuid", required: true },
  { name: "skillIds", type: "array", required: true },
  { name: "declarationAccepted", type: "boolean", required: true },
  { name: "photo", type: "file", required: true },
];

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

function isApiPath(url: string, suffix: string): boolean {
  const { pathname } = new URL(url);
  if (pathname.includes("/competitor/") || pathname.includes("/_next")) {
    return false;
  }
  return pathname.replace(/\/$/, "").endsWith(suffix);
}

function formOut(overrides: Record<string, unknown> = {}) {
  return {
    fields: DEFAULT_FIELDS,
    maxSkills: 1,
    photoMaxMb: 2,
    photoFormats: ["image/jpeg", "image/png"],
    readOnly: false,
    minorAgeUnder: 18,
    minorReferenceDate: "2026-01-01",
    window: {
      opensAt: "2026-01-01T00:00:00",
      closesAt: "2026-12-31T23:59:59",
    },
    ...overrides,
  };
}

async function mockRegistrationForm(
  page: Page,
  body: Record<string, unknown> = formOut(),
): Promise<void> {
  await page.route(
    (url) =>
      isApiPath(url.toString(), `/competitions/${CYCLE_ID}/registration-form`),
    async (route) => {
      if (
        route.request().resourceType() !== "fetch" &&
        route.request().resourceType() !== "xhr"
      ) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, body);
    },
  );
}

type CreateMode =
  | "ok"
  | "field"
  | "photo"
  | "abuse"
  | "duplicate"
  | "window"
  | "skill";

async function mockCreateRegistration(
  page: Page,
  mode: CreateMode,
): Promise<void> {
  await page.route(
    (url) => isApiPath(url.toString(), `/competitions/${CYCLE_ID}/registrations`),
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
      if (mode === "field") {
        await fulfillJson(
          route,
          422,
          envelope("VALIDATION_ERROR", "Missing required field", [
            { name: "givenNames", reason: "REQUIRED" },
          ]),
        );
        return;
      }
      if (mode === "photo") {
        await fulfillJson(
          route,
          422,
          envelope("PHOTO_INVALID", "Photo rejected", [
            { name: "photo", reason: "PHOTO_INVALID" },
          ]),
        );
        return;
      }
      if (mode === "abuse") {
        await fulfillJson(
          route,
          403,
          envelope("ABUSE_SUSPECTED", "CAPTCHA failed", [
            { name: "captchaToken", reason: "ABUSE_SUSPECTED" },
          ]),
        );
        return;
      }
      if (mode === "window") {
        await fulfillJson(
          route,
          403,
          envelope("WINDOW_CLOSED", "Window closed", [
            { name: "window", reason: "WINDOW_CLOSED" },
          ]),
        );
        return;
      }
      if (mode === "skill") {
        await fulfillJson(
          route,
          422,
          envelope("SKILL_SELECTION_INVALID", "Too many skills", [
            { name: "skillIds", reason: "SKILL_SELECTION_INVALID" },
          ]),
        );
        return;
      }
      if (mode === "duplicate") {
        await fulfillJson(route, 201, {
          competitorId: COMPETITOR_ID,
          competitorRef: "WSGH-DUP-001",
          status: "PENDING_REVIEW",
          flags: ["DUPLICATE_SUSPECTED"],
          message: "DUPLICATE_SUSPECTED — admin review pending",
        });
        return;
      }
      await fulfillJson(route, 201, {
        competitorId: COMPETITOR_ID,
        competitorRef: "WSGH-REF-001",
        status: "PENDING_REVIEW",
        flags: [],
        message: null,
      });
    },
  );
}

/** Minimal valid 1x1 PNG for upload tests. */
function tinyPngPath(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scms-e2e-"));
  const file = path.join(dir, "photo.png");
  const buf = Buffer.from(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489" +
      "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082",
    "hex",
  );
  fs.writeFileSync(file, buf);
  return file;
}

async function mockRegistrationDeps(page: Page): Promise<void> {
  await page.route(
    (url) => isApiPath(url.toString(), `/competitions/${CYCLE_ID}/skills:available`),
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
          skillId: SKILL_A,
          name: "Web Development",
          number: "09",
          familyName: "ICT",
          active: true,
        },
        {
          skillId: SKILL_B,
          name: "Graphic Design",
          number: "14",
          familyName: "Creative",
          active: true,
        },
      ]);
    },
  );
  await page.route(
    (url) => isApiPath(url.toString(), "/regions"),
    async (route) => {
      if (
        route.request().resourceType() !== "fetch" &&
        route.request().resourceType() !== "xhr"
      ) {
        await route.fallback();
        return;
      }
      await fulfillJson(route, 200, [
        { regionId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "Greater Accra", active: true },
        { regionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "Ashanti", active: true },
      ]);
    },
  );
  await page.route(
    (url) => {
      const { pathname } = new URL(url.toString());
      return pathname.replace(/\/$/, "").endsWith("/institutions:search");
    },
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
          institutionId: INST_ID,
          code: "ACC-TECH-01",
          name: "Accra Technical Institute",
        },
      ]);
    },
  );
  await page.route(
    (url) =>
      isApiPath(url.toString(), `/competitions/${CYCLE_ID}/registrations/draft`),
    async (route) => {
      if (
        route.request().resourceType() !== "fetch" &&
        route.request().resourceType() !== "xhr"
      ) {
        await route.fallback();
        return;
      }
      const method = route.request().method();
      if (method === "GET") {
        await fulfillJson(
          route,
          404,
          envelope("DRAFT_NOT_FOUND", "No draft"),
        );
        return;
      }
      if (method === "PUT") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        await fulfillJson(route, 200, {
          competitorId: COMPETITOR_ID,
          status: "DRAFT",
          updatedAt: new Date().toISOString(),
          currentStep: body.currentStep ?? 1,
          givenNames: body.givenNames ?? null,
          familyName: body.familyName ?? null,
          skillIds: body.skillIds ?? [],
          hasPhoto: Boolean(body.photo),
        });
        return;
      }
      await route.fallback();
    },
  );
}

async function fillHappyPath(page: Page, opts?: { captcha?: string }) {
  await page.locator("#givenNames").fill("Ama");
  await page.locator("#familyName").fill("Mensah");
  await page.locator("#gender").selectOption("Female");
  await page.locator("#dateOfBirth").fill("2005-03-15");
  await page.locator("#email").fill("ama@example.com");
  await page.locator("#mobile").fill("+233241234567");
  await page.locator("#whatsapp").fill("+233241234567");
  await page.locator("#guardianName").fill("Kofi Mensah");
  await page.locator("#guardianPhone").fill("+233241000111");
  await page.locator("#heardAbout").selectOption("Social media");
  await page.getByTestId("id-kind-GHANA_CARD").click();
  await page.locator("#nationalId").fill("GHA-123456789");
  await page.getByTestId("registration-photo").setInputFiles(tinyPngPath());
  await page.getByTestId("registration-continue").click();

  await expect(page.getByTestId("passport-no")).toBeVisible();
  await page.getByTestId("passport-no").check();
  await page.getByTestId("registration-continue").click();

  await expect(page.getByTestId("affiliation-school")).toBeVisible();
  await page.getByTestId("affiliation-school").check();
  await expect(page.getByTestId("school-search")).toBeVisible();
  await page.getByTestId("school-search").fill("Accra");
  await expect(page.getByTestId("school-search-results")).toBeVisible();
  await page
    .getByRole("option", { name: /Accra Technical Institute/i })
    .click();
  await expect(page.getByTestId("school-selected")).toBeVisible();
  await page.getByTestId("organization-phone").fill("+233302123456");
  await page.getByTestId("organization-email").fill("school@example.com");
  await page.getByTestId("skill-id-0").selectOption(SKILL_A);
  await page.getByTestId("registration-continue").click();

  await expect(page.getByTestId("coach-surname")).toBeVisible();
  await page.getByTestId("coach-surname").fill("Asante");
  await page.getByTestId("coach-firstName").fill("Kojo");
  await page.getByTestId("coach-otherName").fill("Mensah");
  await page.getByTestId("coach-contactNumber").fill("+233201112233");
  await page.getByTestId("coach-email").fill("coach@example.com");
  await page.getByTestId("coach-dateOfBirth").fill("1985-04-12");
  await page.getByTestId("registration-continue").click();

  await expect(page.getByTestId("registration-declaration")).toBeVisible();
  await page.getByTestId("registration-declaration").check();
  await page
    .getByTestId("registration-captcha")
    .fill(opts?.captcha ?? "ok");
}

test.describe("US-REG-01-UI competitor registration", () => {
  test.beforeEach(async ({ page }) => {
    await installCompetitorSession(page);
    await mockRegistrationDeps(page);
  });

  test("US-REG-01-UI-AC1 successful registration shows competitorRef", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "ok");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await fillHappyPath(page);
    await page.getByTestId("registration-submit").click();
    await expect(page).toHaveURL(
      new RegExp(`/competitor/competitions/${CYCLE_ID}/register/confirmation`),
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("registration-confirmation")).toBeVisible();
    await expect(page.getByTestId("competitor-ref")).toHaveText("WSGH-REF-001");
  });

  test("US-REG-01-UI-AC2 window closed disables submit", async ({ page }) => {
    await mockRegistrationForm(
      page,
      formOut({ readOnly: true, window: null }),
    );
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("alert").filter({ hasText: /Registration closed|WINDOW_CLOSED/i }).first(),
    ).toBeVisible();
    await expect(page.getByTestId("registration-continue")).toBeDisabled();
    await expect(page.getByTestId("registration-save-draft")).toBeDisabled();
  });

  test("US-REG-01-UI-AC3 missing required field shows errors without confirmation", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "field");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await fillHappyPath(page);
    await page.getByTestId("registration-back").click();
    await page.getByTestId("registration-back").click();
    await page.getByTestId("registration-back").click();
    await page.getByTestId("registration-back").click();
    await page.locator("#givenNames").fill("");
    await page.getByTestId("registration-continue").click();
    await expect(
      page.getByRole("alert").filter({ hasText: /required|Given names/i }).first(),
    ).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/competitor/competitions/${CYCLE_ID}/register$`),
    );
    await expect(page.getByTestId("registration-confirmation")).toHaveCount(0);
  });

  test("US-REG-01-UI-AC4 invalid photo shows PHOTO_INVALID", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "photo");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await fillHappyPath(page);
    await page.getByTestId("registration-submit").click();
    await expect(
      page.getByRole("alert").filter({ hasText: /Photo|PHOTO_INVALID/i }).first(),
    ).toBeVisible();
    await expect(page.getByTestId("registration-confirmation")).toHaveCount(0);
  });

  test("US-REG-01-UI-AC5 abuse blocked does not invent a reference", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "abuse");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await fillHappyPath(page, { captcha: "bad-token" });
    await page.getByTestId("registration-submit").click();
    await expect(page.getByTestId("registration-abuse-alert")).toBeVisible();
    await expect(
      page.getByRole("alert").filter({ hasText: /Security check|ABUSE_SUSPECTED/i }).first(),
    ).toBeVisible();
    await expect(page.getByTestId("competitor-ref")).toHaveCount(0);
    await expect(page).not.toHaveURL(/confirmation/);
  });

  test("US-REG-01-UI-AC6 duplicate suspected still shows ref with pending check", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "duplicate");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await fillHappyPath(page);
    await page.getByTestId("registration-submit").click();
    await expect(page.getByTestId("competitor-ref")).toHaveText("WSGH-DUP-001", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("duplicate-pending-alert")).toBeVisible();
    await expect(
      page.getByTestId("duplicate-pending-alert").getByText("Check pending"),
    ).toBeVisible();
  });

  test("US-REG-01-UI-AC7 single-skill rule prevents selecting two", async ({
    page,
  }) => {
    await mockRegistrationForm(page, formOut({ maxSkills: 1 }));
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await page.locator("#givenNames").fill("Ama");
    await page.locator("#familyName").fill("Mensah");
    await page.locator("#gender").selectOption("Female");
    await page.locator("#dateOfBirth").fill("2005-03-15");
    await page.locator("#email").fill("ama@example.com");
    await page.locator("#mobile").fill("+233241234567");
    await page.locator("#whatsapp").fill("+233241234567");
    await page.locator("#guardianName").fill("Kofi Mensah");
    await page.locator("#guardianPhone").fill("+233241000111");
    await page.locator("#heardAbout").selectOption("Social media");
    await page.getByTestId("id-kind-GHANA_CARD").click();
    await page.locator("#nationalId").fill("GHA-123456789");
    await page.getByTestId("registration-photo").setInputFiles(tinyPngPath());
    await page.getByTestId("registration-continue").click();
    await page.getByTestId("passport-no").check();
    await page.getByTestId("registration-continue").click();
    await page.getByTestId("affiliation-school").check();
    await page.getByTestId("organization-phone").fill("+233302123456");
    await page.getByTestId("organization-email").fill("school@example.com");
    await expect(page.getByTestId("registration-skills")).toBeVisible();
    await expect(page.getByTestId("skill-id-0")).toBeVisible();
    await expect(page.getByTestId("skill-add")).toHaveCount(0);
    await page.getByTestId("skill-id-0").selectOption(SKILL_A);
    // Only one slot exists; second skill input must not appear.
    await expect(page.getByTestId("skill-id-1")).toHaveCount(0);
    // Sanity: selecting SKILL_B replaces rather than stacking.
    await page.getByTestId("skill-id-0").selectOption(SKILL_B);
    await expect(page.getByTestId("skill-id-0")).toHaveValue(SKILL_B);
  });

  test("affiliation company path requires city and region", async ({
    page,
  }) => {
    await mockRegistrationForm(page);
    await mockCreateRegistration(page, "ok");
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await page.locator("#givenNames").fill("Ama");
    await page.locator("#familyName").fill("Mensah");
    await page.locator("#gender").selectOption("Female");
    await page.locator("#dateOfBirth").fill("2005-03-15");
    await page.locator("#email").fill("ama@example.com");
    await page.locator("#mobile").fill("+233241234567");
    await page.locator("#whatsapp").fill("+233241234567");
    await page.locator("#guardianName").fill("Kofi Mensah");
    await page.locator("#guardianPhone").fill("+233241000111");
    await page.locator("#heardAbout").selectOption("Other means");
    await page.getByTestId("id-kind-OTHER").click();
    await page.getByTestId("other-id-type").selectOption("Passport");
    await page.locator("#nationalId").fill("P1234567");
    await page.getByTestId("registration-photo").setInputFiles(tinyPngPath());
    await page.getByTestId("registration-continue").click();
    await page.getByTestId("passport-no").check();
    await page.getByTestId("registration-continue").click();

    await page.getByTestId("affiliation-company").check();
    await page.getByTestId("organization-name").fill("Acme Skills Ltd");
    await page.getByTestId("region-select").selectOption({ label: "Greater Accra" });
    await page.getByTestId("organization-city").fill("Accra");
    await page.getByTestId("organization-phone").fill("+233302123456");
    await page.getByTestId("organization-email").fill("hr@acme.example");
    await page.getByTestId("skill-id-0").selectOption(SKILL_A);
    await page.getByTestId("registration-continue").click();

    await page.getByTestId("coach-surname").fill("Asante");
    await page.getByTestId("coach-firstName").fill("Kojo");
    await page.getByTestId("coach-contactNumber").fill("+233201112233");
    await page.getByTestId("coach-email").fill("coach@example.com");
    await page.getByTestId("coach-dateOfBirth").fill("1985-04-12");
    await page.getByTestId("registration-continue").click();
    await page.getByTestId("registration-declaration").check();
    await page.getByTestId("registration-submit").click();
    await expect(page.getByTestId("competitor-ref")).toHaveText("WSGH-REF-001", {
      timeout: 15_000,
    });
  });

  test("manual school path requires region", async ({ page }) => {
    await mockRegistrationForm(page);
    await page.goto(`/competitor/competitions/${CYCLE_ID}/register`);
    await expect(page.getByTestId("registration-form")).toBeVisible({
      timeout: 15_000,
    });
    await page.locator("#givenNames").fill("Ama");
    await page.locator("#familyName").fill("Mensah");
    await page.locator("#gender").selectOption("Female");
    await page.locator("#dateOfBirth").fill("2005-03-15");
    await page.locator("#email").fill("ama@example.com");
    await page.locator("#mobile").fill("+233241234567");
    await page.locator("#whatsapp").fill("+233241234567");
    await page.locator("#guardianName").fill("Kofi Mensah");
    await page.locator("#guardianPhone").fill("+233241000111");
    await page.locator("#heardAbout").selectOption("Friend");
    await page.getByTestId("id-kind-GHANA_CARD").click();
    await page.locator("#nationalId").fill("GHA-123456789");
    await page.getByTestId("registration-photo").setInputFiles(tinyPngPath());
    await page.getByTestId("registration-continue").click();
    await page.getByTestId("passport-no").check();
    await page.getByTestId("registration-continue").click();

    await page.getByTestId("affiliation-school").check();
    await page.getByTestId("school-not-listed").click();
    await page.getByTestId("manual-school-name").fill("New Community SHS");
    await page.getByTestId("organization-phone").fill("+233302123456");
    await page.getByTestId("organization-email").fill("school@example.com");
    await page.getByTestId("skill-id-0").selectOption(SKILL_A);
    await page.getByTestId("registration-continue").click();
    await expect(
      page.getByRole("alert").filter({ hasText: /region|highlighted/i }).first(),
    ).toBeVisible();
    await page.getByTestId("region-select").selectOption({ label: "Ashanti" });
    await page.getByTestId("registration-continue").click();
    await expect(page.getByTestId("coach-surname")).toBeVisible();
  });
});
