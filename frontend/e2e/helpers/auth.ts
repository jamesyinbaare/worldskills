import type { Page } from "@playwright/test";

/** Must match keys in `frontend/lib/api.ts`. */
export const ACCESS_TOKEN_KEY = "scms_access_token";
export const REFRESH_TOKEN_KEY = "scms_refresh_token";

export const E2E_ADMIN = {
  id: "00000000-0000-4000-8000-0000000000ad",
  email: "e2e-admin@example.com",
  full_name: "E2E Admin",
  role: "SUPER_ADMIN",
};

export const E2E_INSTITUTION = {
  id: "00000000-0000-4000-8000-0000000000in",
  email: "e2e-institution@example.com",
  full_name: "E2E Institution",
  role: "INSTITUTION",
  institutionId: "99999999-9999-4999-8999-999999999999",
};

export const E2E_COMPETITOR = {
  id: "00000000-0000-4000-8000-0000000000co",
  email: "e2e-competitor@example.com",
  full_name: "E2E Competitor",
  role: "COMPETITOR",
};

type MeStub = {
  id: string;
  email: string;
  full_name: string;
  role: string;
};

async function installSession(page: Page, me: MeStub): Promise<void> {
  await page.addInitScript(
    ({ accessKey, refreshKey, user }) => {
      localStorage.setItem(accessKey, "e2e-access-token");
      localStorage.setItem(refreshKey, "e2e-refresh-token");

      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;

        if (url.includes("/auth/me")) {
          return new Response(JSON.stringify(user), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/auth/refresh")) {
          return new Response(
            JSON.stringify({
              access_token: "e2e-access-token",
              refresh_token: "e2e-refresh-token",
              token_type: "bearer",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }
        return originalFetch(input, init);
      };
    },
    {
      accessKey: ACCESS_TOKEN_KEY,
      refreshKey: REFRESH_TOKEN_KEY,
      user: me,
    },
  );
}

/**
 * Seed tokens and stub auth fetch in-page so RoleGate works even when
 * page.route URL matching does not catch the baked-in API host.
 */
export async function installAdminSession(page: Page): Promise<void> {
  await installSession(page, E2E_ADMIN);
}

export async function installInstitutionSession(page: Page): Promise<void> {
  await installSession(page, E2E_INSTITUTION);
}

export async function installCompetitorSession(page: Page): Promise<void> {
  await installSession(page, E2E_COMPETITOR);
}
