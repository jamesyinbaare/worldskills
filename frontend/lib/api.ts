/** API client for SCMS backend — parses standard error envelope. */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type FieldError = { name: string; reason: string };

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    fields: FieldError[];
    traceId: string;
  };
};

export class ApiError extends Error {
  code: string;
  fields: FieldError[];
  status: number;
  traceId: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.fields = body.error.fields || [];
    this.traceId = body.error.traceId;
  }
}

const TOKEN_KEY = "scms_access_token";
const REFRESH_KEY = "scms_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let body: ApiErrorBody;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      body = {
        error: {
          code: "HTTP_ERROR",
          message: res.statusText || "Request failed",
          fields: [],
          traceId: "",
        },
      };
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export type Me = {
  id: string;
  email: string | null;
  full_name: string;
  role: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type CycleListItem = {
  cycleId: string;
  name: string;
  status: string;
  period: { start: string; end: string };
  timeZone: string;
  languages: string[];
};

export type CycleOut = {
  cycleId: string;
  status: string;
  name?: string | null;
  period?: { start: string; end: string } | null;
  timeZone?: string | null;
  languages?: string[] | null;
};

export type ValidateOut = {
  ok: boolean;
  issues: { code: string; entity: string; message: string; link: string }[];
};

export async function login(email: string, password: string): Promise<Me> {
  const tokens = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setTokens(tokens.access_token, tokens.refresh_token);
  return apiFetch<Me>("/auth/me");
}

export async function fetchMe(): Promise<Me> {
  return apiFetch<Me>("/auth/me");
}

export function isAdminRole(role: string): boolean {
  return role === "ADMIN" || role === "SUPER_ADMIN";
}
