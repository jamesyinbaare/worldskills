import { test, expect, type Page, type Route } from "@playwright/test";
import { installAdminSession } from "./helpers/auth";

const CYCLE_ID = "11111111-1111-4111-8111-111111111111";
const NOMINATION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const NOMINATION_ID_2 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

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

async function seedPendingQueue(
  page: Page,
  rows: {
    nominationId: string;
    competitorRef: string;
    status?: string;
  }[],
): Promise<void> {
  await page.addInitScript(
    ({ competitionId, items }) => {
      sessionStorage.setItem(
        `scms_nominations_${competitionId}`,
        JSON.stringify(
          items.map((r) => ({
            nominationId: r.nominationId,
            status: r.status ?? "PENDING_REVIEW",
            competitorRef: r.competitorRef,
          })),
        ),
      );
    },
    { competitionId: CYCLE_ID, items: rows },
  );
}

async function mockApprove(page: Page): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url);
      return (
        !pathname.includes("/admin/") &&
        pathname.includes(`:approve`) &&
        pathname.includes("/nominations/")
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
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      const path = new URL(route.request().url()).pathname;
      const id = path.split("/nominations/")[1]?.split(":")[0];
      await fulfillJson(route, 200, {
        nominationId: id,
        status: "APPROVED",
        competitorId: null,
        reason: null,
      });
    },
  );
}

async function mockReject(page: Page, mode: "ok" | "required"): Promise<void> {
  await page.route(
    (url) => {
      const { pathname } = new URL(url);
      return (
        !pathname.includes("/admin/") &&
        pathname.includes(":reject") &&
        pathname.includes("/nominations/")
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
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      if (mode === "required") {
        await fulfillJson(
          route,
          422,
          envelope("REASON_REQUIRED", "Reason required", [
            { name: "reason", reason: "REASON_REQUIRED" },
          ]),
        );
        return;
      }
      const body = route.request().postDataJSON() as { reason?: string };
      const path = new URL(route.request().url()).pathname;
      const id = path.split("/nominations/")[1]?.split(":")[0];
      await fulfillJson(route, 200, {
        nominationId: id,
        status: "REJECTED",
        competitorId: null,
        reason: body.reason ?? null,
      });
    },
  );
}

test.describe("US-INS-01-UI admin nomination queue", () => {
  test.beforeEach(async ({ page }) => {
    await installAdminSession(page);
  });

  test("US-INS-01-UI-AC3 admin approve updates status", async ({ page }) => {
    await seedPendingQueue(page, [
      { nominationId: NOMINATION_ID, competitorRef: "pending-one" },
    ]);
    await mockApprove(page);

    await page.goto(`/admin/competitions/${CYCLE_ID}/nominations`);
    await expect(page.getByTestId("admin-nomination-queue")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("admin-nomination-row")).toHaveCount(1);

    await page.getByTestId(`approve-${NOMINATION_ID}`).click();
    await expect(page.getByTestId("admin-nomination-row")).toHaveCount(0);
    await expect(page.getByTestId("resolved-nomination-row")).toHaveAttribute(
      "data-status",
      "APPROVED",
    );
  });

  test("US-INS-01-UI-AC4 reject without reason blocked; with reason REJECTED", async ({
    page,
  }) => {
    await seedPendingQueue(page, [
      { nominationId: NOMINATION_ID_2, competitorRef: "pending-two" },
    ]);
    await mockReject(page, "ok");

    await page.goto(`/admin/competitions/${CYCLE_ID}/nominations`);
    await expect(page.getByTestId(`reject-open-${NOMINATION_ID_2}`)).toBeVisible({
      timeout: 15_000,
    });
    await page.getByTestId(`reject-open-${NOMINATION_ID_2}`).click();
    await expect(page.getByTestId("reject-dialog")).toBeVisible();

    await page.getByTestId("reject-submit").click();
    await expect(page.locator("#reject-reason-error")).toHaveText(
      "REASON_REQUIRED",
    );
    await expect(page.getByTestId("admin-nomination-row")).toHaveCount(1);

    await page.locator("#reject-reason").fill("Documents incomplete");
    await page.getByTestId("reject-submit").click();

    await expect(page.getByTestId("admin-nomination-row")).toHaveCount(0);
    const resolved = page.getByTestId("resolved-nomination-row");
    await expect(resolved).toHaveAttribute("data-status", "REJECTED");
    await expect(resolved).toContainText("Documents incomplete");
  });
});
