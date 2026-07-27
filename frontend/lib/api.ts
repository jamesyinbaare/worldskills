/** API client for SCMS backend — parses standard error envelope; refresh-on-401. */

function getApiBase(): string {
  const forced = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (forced) return forced;

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    // worldskills.X → worldskills-api.X (same-parent dual hosts)
    if (host.startsWith("worldskills.")) {
      return `https://${host.replace(/^worldskills\./, "worldskills-api.")}`;
    }
  }

  const internal = process.env.INTERNAL_API_BASE_URL?.replace(/\/$/, "");
  if (internal) return internal;

  return "http://localhost:8000";
}

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

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${getApiBase()}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!res.ok) {
          clearTokens();
          return false;
        }
        const tokens = (await res.json()) as TokenResponse;
        setTokens(tokens.access_token, tokens.refresh_token);
        return true;
      } catch {
        clearTokens();
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }

  return refreshInFlight;
}

async function parseError(res: Response): Promise<ApiError> {
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
  return new ApiError(res.status, body);
}

export type ApiFetchOptions = RequestInit & {
  /** Skip refresh-on-401 (used for login/refresh themselves). */
  skipAuthRetry?: boolean;
};

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { skipAuthRetry, ...init } = options;
  const headers = new Headers(init.headers);
  const bodyIsBinary =
    typeof Blob !== "undefined" && init.body instanceof Blob
      ? true
      : init.body instanceof ArrayBuffer ||
        ArrayBuffer.isView(init.body);
  const bodyIsFormData =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  if (
    !headers.has("Content-Type") &&
    init.body &&
    !bodyIsBinary &&
    !bodyIsFormData
  ) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${getApiBase()}${path}`, { ...init, headers });

  if (res.status === 401 && !skipAuthRetry) {
    const refreshed = await tryRefreshTokens();
    if (refreshed) {
      const retryHeaders = new Headers(init.headers);
      if (
        !retryHeaders.has("Content-Type") &&
        init.body &&
        !bodyIsBinary &&
        !bodyIsFormData
      ) {
        retryHeaders.set("Content-Type", "application/json");
      }
      const access = getAccessToken();
      if (access) {
        retryHeaders.set("Authorization", `Bearer ${access}`);
      }
      const retry = await fetch(`${getApiBase()}${path}`, {
        ...init,
        headers: retryHeaders,
      });
      if (!retry.ok) throw await parseError(retry);
      if (retry.status === 204) return undefined as T;
      return (await retry.json()) as T;
    }
    clearTokens();
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utfMatch?.[1]) {
    try {
      return decodeURIComponent(utfMatch[1].trim());
    } catch {
      return utfMatch[1].trim();
    }
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(header);
  return plainMatch?.[1]?.trim() ?? null;
}

/** Authenticated fetch that returns a Blob (for file downloads). */
export async function apiFetchBlob(
  path: string,
  options: ApiFetchOptions = {},
): Promise<{ blob: Blob; filename: string | null; contentType: string | null }> {
  const { skipAuthRetry, ...init } = options;
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res = await fetch(`${getApiBase()}${path}`, { ...init, headers });

  if (res.status === 401 && !skipAuthRetry) {
    const refreshed = await tryRefreshTokens();
    if (refreshed) {
      const retryHeaders = new Headers(init.headers);
      const access = getAccessToken();
      if (access) {
        retryHeaders.set("Authorization", `Bearer ${access}`);
      }
      res = await fetch(`${getApiBase()}${path}`, {
        ...init,
        headers: retryHeaders,
      });
    } else {
      clearTokens();
    }
  }

  if (!res.ok) throw await parseError(res);
  const blob = await res.blob();
  return {
    blob,
    filename: filenameFromContentDisposition(
      res.headers.get("Content-Disposition"),
    ),
    contentType: res.headers.get("Content-Type"),
  };
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export type Me = {
  id: string;
  email: string | null;
  full_name: string;
  role: string;
  must_change_password?: boolean;
  institutionId?: string | null;
  institution_id?: string | null;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password?: boolean;
  mustChangePassword?: boolean;
};

export type UserOut = {
  userId: string;
  email: string;
  fullName: string;
  role: string;
  institutionId?: string | null;
  isActive: boolean;
  mustChangePassword: boolean;
};

export type CreateUserResponse = UserOut & {
  temporaryPassword?: string | null;
  inviteSent?: boolean;
};

export type InstitutionOut = {
  institutionId: string;
  code: string;
  name: string;
  regionId: string | null;
  active: boolean;
};

/** @deprecated Prefer InstitutionOut — kept for call sites that only need id/name. */
export type InstitutionListItem = InstitutionOut;

export type InstitutionCreateInput = {
  code: string;
  name: string;
  regionId: string;
  active?: boolean;
};

export type InstitutionPatchInput = {
  code?: string;
  name?: string;
  regionId?: string;
  active?: boolean;
};

export type InstitutionImportError = {
  row: number;
  message?: string;
  field?: string;
  reason?: string;
};

export type InstitutionImportResult = {
  created: number;
  updated: number;
  errors: InstitutionImportError[];
};

export type CompetitionListItem = {
  competitionId: string;
  name: string;
  status: string;
  period: { start: string; end: string };
  timeZone: string;
  languages: string[];
};

export type CompetitionOut = {
  competitionId: string;
  status: string;
  name?: string | null;
  period?: { start: string; end: string } | null;
  timeZone?: string | null;
  languages?: string[] | null;
  description?: string | null;
};

export type ValidateOut = {
  ok: boolean;
  issues: { code: string; entity: string; message: string; link: string }[];
};

export type SkillOut = {
  skillId: string;
  cycleSkillId?: string | null;
  competitionId: string;
  catalogSkillId?: string | null;
  name: string;
  number?: string | null;
  familyId?: string | null;
  familyName?: string | null;
  ageRuleId?: string | null;
  ageRule?: {
    maxAge: number;
    referenceDate?: string | null;
    openCategoryEnabled: boolean;
  } | null;
  pathwayId?: string | null;
  schemeId?: string | null;
  capacity?: number | null;
  schoolQuota?: number | null;
  active: boolean;
  hasPathway?: boolean;
  hasCriteriaDocument?: boolean;
  criteriaFileName?: string | null;
  criteriaScanStatus?: string | null;
};

export type FamilyOut = {
  familyId: string;
  name: string;
  description?: string | null;
  active: boolean;
};

export type CatalogSkillOut = {
  skillId: string;
  name: string;
  number?: string | null;
  familyId: string;
  familyName?: string | null;
  description?: string | null;
  active: boolean;
};

export type SkillCreateInput = {
  name?: string;
  number?: string | null;
  familyId?: string | null;
  ageRuleId?: string | null;
  pathwayId?: string | null;
  schemeId?: string | null;
  capacity?: number | null;
  skillId?: string;
  ageRule?: {
    maxAge: number;
    referenceDate?: string | null;
    openCategoryEnabled: boolean;
  };
};

export type CompetitionSkillAssociateInput = {
  skillId: string;
  ageRule: {
    maxAge: number;
    referenceDate?: string | null;
    openCategoryEnabled: boolean;
  };
  capacity?: number | null;
};

export type StagePathwayItem = {
  order: number;
  type: string;
  selectionMode: "PER_ZONE" | "NATIONAL_POOL";
  schemeId?: string | null;
  opensAt?: string | null;
  closesAt?: string | null;
  branch?: Record<string, unknown> | null;
  quotaByZone?: Record<string, number> | null;
  quota?: number | null;
  minScore?: number | null;
};

export type StageOut = {
  stageId: string;
  order: number;
  type: string;
  selectionMode: string;
  schemeId?: string | null;
  exerciseStatus?: string | null;
  opensAt?: string | null;
  closesAt?: string | null;
  branch?: Record<string, unknown> | null;
  quotaByZone?: Record<string, number> | null;
  minScore?: number | null;
  quota?: number | null;
};

export type RegionOut = {
  regionId: string;
  name: string;
  active: boolean;
};

export type ZoneOut = {
  zoneId: string;
  name: string;
  active: boolean;
};

export type RegionZoneMapOut = {
  mappings: { regionId: string; zoneId: string }[];
};

export type DeliverableItem = {
  code: string;
  label?: string | null;
  required?: boolean;
  allowedTypes?: string[];
  maxSizeBytes?: number | null;
};

export type ExerciseOut = {
  exerciseId: string;
  stageId: string;
  competitionId: string;
  title: string;
  brief?: string | null;
  deliverables: DeliverableItem[];
  status: string;
  schemeId?: string | null;
  latePolicy?: string | null;
  timedDurationSeconds?: number | null;
  packFileName?: string | null;
  packContentType?: string | null;
  packScanStatus?: string | null;
  hasRubricCriteria?: boolean;
  blindMode?: boolean | null;
  criteriaCount?: number;
};

export type RubricCriterion = {
  id?: string;
  name: string;
  type: "MEASUREMENT" | "JUDGEMENT" | string;
  max: number;
};

export type RubricPenalty = {
  code: string;
  deduction: number;
  cap?: number | null;
};

export type ExerciseRubricOut = {
  schemeId: string;
  competitionId: string;
  stageId: string;
  exerciseId: string;
  name: string;
  blindMode: boolean;
  criteria: RubricCriterion[];
  penalties: RubricPenalty[];
  hasRubricCriteria: boolean;
};

export type ExerciseRubricPutInput = {
  blindMode?: boolean;
  criteria: RubricCriterion[];
  penalties?: RubricPenalty[];
};

export type ExercisePutInput = {
  title: string;
  brief?: string | null;
  deliverables?: DeliverableItem[];
  schemeId?: string | null;
  latePolicy?: string | null;
  timedDurationSeconds?: number | null;
};

export type PathwayOut = {
  stages: StageOut[];
  finalistsPerSkill: number;
};

export type AssignmentOut = {
  assignmentId: string;
  competitionId: string;
  expertId: string;
  skillId: string;
  cycleSkillId?: string | null;
  zoneId: string;
  coiFlags: {
    institutionId: string;
    reason: string;
    competitorIds: string[];
  }[];
};

export type AssignmentCreateInput = {
  expertId: string;
  skillId?: string;
  cycleSkillId?: string;
  zoneId: string;
};

export type AgeRuleOut = {
  ageRuleId: string;
  competitionId: string;
  name: string;
  maxAge: number;
  referenceDate?: string | null;
  openCategoryEnabled: boolean;
};

export type AgeRuleCreateInput = {
  name: string;
  maxAge: number;
  referenceDate?: string | null;
  openCategoryEnabled?: boolean;
};

export type PathwayConfigOut = {
  pathwayId: string;
  competitionId: string;
  name: string;
};

export type PathwayConfigCreateInput = {
  name: string;
};

export type MarkingSchemeOut = {
  schemeId: string;
  competitionId: string;
  name: string;
  documentFileName?: string | null;
  documentContentType?: string | null;
  documentScanStatus?: string | null;
  blindMode?: boolean | null;
  criteria?: RubricCriterion[] | null;
  penalties?: RubricPenalty[] | null;
  hasRubricCriteria?: boolean;
};

export type MarkingSchemeCreateInput = {
  name: string;
};

export async function listFamilies(): Promise<FamilyOut[]> {
  return apiFetch<FamilyOut[]>("/families");
}

export async function createFamily(payload: {
  name: string;
  description?: string | null;
}): Promise<FamilyOut> {
  return apiFetch<FamilyOut>("/families", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function patchFamily(
  familyId: string,
  payload: { name?: string; description?: string | null; active?: boolean },
): Promise<FamilyOut> {
  return apiFetch<FamilyOut>(`/families/${familyId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listCatalogSkills(opts?: {
  active?: boolean;
}): Promise<CatalogSkillOut[]> {
  const params = new URLSearchParams();
  if (opts?.active === true) params.set("active", "true");
  const q = params.toString();
  return apiFetch<CatalogSkillOut[]>(`/skills${q ? `?${q}` : ""}`);
}

export async function createCatalogSkill(payload: {
  name: string;
  number?: string | null;
  familyId: string;
  description?: string | null;
}): Promise<CatalogSkillOut> {
  return apiFetch<CatalogSkillOut>("/skills", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function patchCatalogSkill(
  skillId: string,
  payload: {
    name?: string;
    number?: string | null;
    familyId?: string;
    description?: string | null;
    active?: boolean;
  },
): Promise<CatalogSkillOut> {
  return apiFetch<CatalogSkillOut>(`/skills/${skillId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listSkills(competitionId: string): Promise<SkillOut[]> {
  return apiFetch<SkillOut[]>(`/competitions/${competitionId}/skills`);
}

export async function createSkill(
  competitionId: string,
  payload: SkillCreateInput | CompetitionSkillAssociateInput,
): Promise<SkillOut> {
  return apiFetch<SkillOut>(`/competitions/${competitionId}/skills`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function associateSkill(
  competitionId: string,
  payload: CompetitionSkillAssociateInput,
): Promise<SkillOut> {
  return createSkill(competitionId, payload);
}

export async function patchCycleSkill(
  competitionId: string,
  cycleSkillId: string,
  payload: {
    ageRule?: {
      maxAge: number;
      referenceDate?: string | null;
      openCategoryEnabled: boolean;
    };
    capacity?: number | null;
    active?: boolean;
  },
): Promise<SkillOut> {
  return apiFetch<SkillOut>(`/competitions/${competitionId}/skills/${cycleSkillId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listAgeRules(competitionId: string): Promise<AgeRuleOut[]> {
  return apiFetch<AgeRuleOut[]>(`/competitions/${competitionId}/age-rules`);
}

export async function createAgeRule(
  competitionId: string,
  payload: AgeRuleCreateInput,
): Promise<AgeRuleOut> {
  return apiFetch<AgeRuleOut>(`/competitions/${competitionId}/age-rules`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listPathways(
  competitionId: string,
): Promise<PathwayConfigOut[]> {
  return apiFetch<PathwayConfigOut[]>(`/competitions/${competitionId}/pathways`);
}

export async function createPathway(
  competitionId: string,
  payload: PathwayConfigCreateInput,
): Promise<PathwayConfigOut> {
  return apiFetch<PathwayConfigOut>(`/competitions/${competitionId}/pathways`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMarkingSchemes(
  competitionId: string,
): Promise<MarkingSchemeOut[]> {
  return apiFetch<MarkingSchemeOut[]>(`/competitions/${competitionId}/marking-schemes`);
}

export async function createMarkingScheme(
  competitionId: string,
  payload: MarkingSchemeCreateInput,
): Promise<MarkingSchemeOut> {
  return apiFetch<MarkingSchemeOut>(`/competitions/${competitionId}/marking-schemes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listRegions(): Promise<RegionOut[]> {
  return apiFetch<RegionOut[]>("/regions");
}

export async function listCycleZones(competitionId: string): Promise<ZoneOut[]> {
  return apiFetch<ZoneOut[]>(`/competitions/${competitionId}/zones`);
}

export async function createCycleZone(
  competitionId: string,
  payload: { name: string },
): Promise<ZoneOut> {
  return apiFetch<ZoneOut>(`/competitions/${competitionId}/zones`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function patchCycleZone(
  competitionId: string,
  zoneId: string,
  payload: { name?: string; active?: boolean },
): Promise<ZoneOut> {
  return apiFetch<ZoneOut>(`/competitions/${competitionId}/zones/${zoneId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getRegionZoneMap(
  competitionId: string,
): Promise<RegionZoneMapOut> {
  return apiFetch<RegionZoneMapOut>(`/competitions/${competitionId}/region-zone-map`);
}

export async function putRegionZoneMap(
  competitionId: string,
  mappings: { regionId: string; zoneId: string }[],
): Promise<RegionZoneMapOut> {
  return apiFetch<RegionZoneMapOut>(`/competitions/${competitionId}/region-zone-map`, {
    method: "PUT",
    body: JSON.stringify({ mappings }),
  });
}

export async function putPathway(
  competitionId: string,
  skillId: string,
  stages: StagePathwayItem[],
): Promise<PathwayOut> {
  return apiFetch<PathwayOut>(
    `/competitions/${competitionId}/skills/${skillId}/pathway`,
    {
      method: "PUT",
      body: JSON.stringify({ stages }),
    },
  );
}

export async function getPathway(
  competitionId: string,
  skillId: string,
): Promise<PathwayOut> {
  return apiFetch<PathwayOut>(`/competitions/${competitionId}/skills/${skillId}/pathway`);
}

export async function getExercise(
  competitionId: string,
  stageId: string,
): Promise<ExerciseOut> {
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise`,
  );
}

export async function putExercise(
  competitionId: string,
  stageId: string,
  payload: ExercisePutInput,
): Promise<ExerciseOut> {
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function publishExercise(
  competitionId: string,
  stageId: string,
): Promise<ExerciseOut> {
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise:publish`,
    { method: "POST" },
  );
}

export async function unpublishExercise(
  competitionId: string,
  stageId: string,
): Promise<ExerciseOut> {
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise:unpublish`,
    { method: "POST" },
  );
}

export async function uploadExercisePack(
  competitionId: string,
  stageId: string,
  file: File,
): Promise<ExerciseOut> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise/pack`,
    { method: "POST", body },
  );
}

export async function deleteExercisePack(
  competitionId: string,
  stageId: string,
): Promise<ExerciseOut> {
  return apiFetch<ExerciseOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise/pack`,
    { method: "DELETE" },
  );
}

export async function downloadExercisePack(
  competitionId: string,
  stageId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitions/${competitionId}/stages/${stageId}/exercise/pack`,
  );
  return { blob, filename: filename || "challenge-pack" };
}

export async function getExerciseRubric(
  competitionId: string,
  stageId: string,
): Promise<ExerciseRubricOut> {
  return apiFetch<ExerciseRubricOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise/rubric`,
  );
}

export async function putExerciseRubric(
  competitionId: string,
  stageId: string,
  payload: ExerciseRubricPutInput,
): Promise<ExerciseRubricOut> {
  return apiFetch<ExerciseRubricOut>(
    `/competitions/${competitionId}/stages/${stageId}/exercise/rubric`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function uploadSkillCriteriaDocument(
  competitionId: string,
  skillId: string,
  file: File,
): Promise<SkillOut> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<SkillOut>(
    `/competitions/${competitionId}/skills/${skillId}/criteria-document`,
    { method: "POST", body },
  );
}

export async function deleteSkillCriteriaDocument(
  competitionId: string,
  skillId: string,
): Promise<SkillOut> {
  return apiFetch<SkillOut>(
    `/competitions/${competitionId}/skills/${skillId}/criteria-document`,
    { method: "DELETE" },
  );
}

export async function downloadSkillCriteriaDocument(
  competitionId: string,
  skillId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitions/${competitionId}/skills/${skillId}/criteria-document`,
  );
  return { blob, filename: filename || "skill-criteria" };
}

export async function downloadPublicSkillCriteriaDocument(
  competitionId: string,
  skillId: string,
): Promise<{ blob: Blob; filename: string; contentType: string | null }> {
  const { blob, filename, contentType } = await apiFetchBlob(
    `/competitions/${competitionId}/public/skills/${skillId}/criteria-document`,
    { skipAuthRetry: true },
  );
  return {
    blob,
    filename: filename || "skill-criteria",
    contentType,
  };
}

export async function uploadMarkingSchemeDocument(
  competitionId: string,
  schemeId: string,
  file: File,
): Promise<MarkingSchemeOut> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<MarkingSchemeOut>(
    `/competitions/${competitionId}/marking-schemes/${schemeId}/document`,
    { method: "POST", body },
  );
}

export async function deleteMarkingSchemeDocument(
  competitionId: string,
  schemeId: string,
): Promise<MarkingSchemeOut> {
  return apiFetch<MarkingSchemeOut>(
    `/competitions/${competitionId}/marking-schemes/${schemeId}/document`,
    { method: "DELETE" },
  );
}

export async function downloadMarkingSchemeDocument(
  competitionId: string,
  schemeId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitions/${competitionId}/marking-schemes/${schemeId}/document`,
  );
  return { blob, filename: filename || "marking-scheme" };
}

export async function listAssignments(
  competitionId: string,
  opts?: { cycleSkillId?: string },
): Promise<AssignmentOut[]> {
  const params = new URLSearchParams();
  if (opts?.cycleSkillId) params.set("cycleSkillId", opts.cycleSkillId);
  const q = params.toString();
  const out = await apiFetch<{ items: AssignmentOut[] }>(
    `/competitions/${competitionId}/assignments${q ? `?${q}` : ""}`,
  );
  return out.items;
}

export async function createAssignment(
  competitionId: string,
  payload: AssignmentCreateInput,
): Promise<AssignmentOut> {
  return apiFetch<AssignmentOut>(`/competitions/${competitionId}/assignments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type NominationOut = {
  nominationId: string;
  status: string;
  competitorId?: string | null;
  reason?: string | null;
};

export type NominationCreateInput = {
  institutionId: string;
  skillId: string;
  competitorRef: string;
  regionId?: string | null;
};

export async function createNomination(
  competitionId: string,
  payload: NominationCreateInput,
): Promise<NominationOut> {
  return apiFetch<NominationOut>(`/competitions/${competitionId}/nominations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function approveNomination(
  nominationId: string,
): Promise<NominationOut> {
  return apiFetch<NominationOut>(`/nominations/${nominationId}:approve`, {
    method: "POST",
  });
}

export async function rejectNomination(
  nominationId: string,
  reason: string,
): Promise<NominationOut> {
  return apiFetch<NominationOut>(`/nominations/${nominationId}:reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export type RegistrationFormField = {
  name: string;
  type: string;
  required: boolean;
  maxLength?: number | null;
  pattern?: string | null;
  allowedValues?: string[] | null;
};

export type RegistrationFormOut = {
  fields: RegistrationFormField[];
  maxSkills: number;
  photoMaxMb: number;
  photoFormats: string[];
  readOnly: boolean;
  window?: { opensAt: string; closesAt: string } | null;
};

export type RegistrationPhotoIn = {
  contentBase64: string;
  contentType: string;
};

export type RegistrationCreateInput = {
  givenNames?: string | null;
  familyName?: string | null;
  gender?: string | null;
  dateOfBirth?: string | null;
  email?: string | null;
  mobile?: string | null;
  whatsapp?: string | null;
  nationalId?: string | null;
  hasPassport?: boolean | null;
  passportNumber?: string | null;
  passportExpiresOn?: string | null;
  institutionId?: string | null;
  regionId?: string | null;
  zoneId?: string | null;
  skillIds?: string[];
  coach?: Record<string, unknown> | null;
  declarationAccepted?: boolean | null;
  photo?: RegistrationPhotoIn | null;
  captchaToken?: string | null;
  guardianName?: string | null;
  guardianEmail?: string | null;
  guardianPhone?: string | null;
};

export type RegistrationOut = {
  competitorId: string;
  competitorRef: string;
  status: string;
  flags: string[];
  message?: string | null;
};

export async function getRegistrationForm(
  competitionId: string,
): Promise<RegistrationFormOut> {
  return apiFetch<RegistrationFormOut>(
    `/competitions/${competitionId}/registration-form`,
  );
}

export async function createRegistration(
  competitionId: string,
  payload: RegistrationCreateInput,
  idempotencyKey: string,
): Promise<RegistrationOut> {
  if (!getAccessToken()) {
    throw new ApiError(401, {
      error: {
        code: "UNAUTHORIZED",
        message: "Sign in to register for a competition.",
        fields: [],
        traceId: "",
      },
    });
  }
  return apiFetch<RegistrationOut>(`/competitions/${competitionId}/registrations`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(payload),
  });
}

export type OpenCompetitionOut = {
  competitionId: string;
  name: string;
  status: string;
  description?: string | null;
  window?: { opensAt: string; closesAt: string } | null;
};

export type PublicSkillOut = {
  skillId: string;
  name: string;
  number?: string | null;
  familyName?: string | null;
  hasCriteriaDocument?: boolean;
  criteriaFileName?: string | null;
};

export type PublicCompetitionOut = {
  competitionId: string;
  name: string;
  description?: string | null;
  period: { start: string; end: string };
  timeZone: string;
  window?: { opensAt: string; closesAt: string } | null;
  skills: PublicSkillOut[];
};

export type AvailableSkillOut = {
  skillId: string;
  name: string;
  number?: string | null;
  familyName?: string | null;
  active: boolean;
  hasCriteriaDocument?: boolean;
  criteriaFileName?: string | null;
};

export type InstitutionLookupOut = {
  code: string;
  name: string;
  institutionId: string;
};

export async function listOpenCompetitions(): Promise<OpenCompetitionOut[]> {
  return apiFetch<OpenCompetitionOut[]>("/competitions:open-for-registration", {
    skipAuthRetry: true,
  });
}

export type MyRegistrationOut = {
  competitorId: string;
  competitionId: string;
  competitionName: string;
  skillId: string;
  skillName: string;
  status: string;
  zoneId?: string | null;
  consentParticipationAt?: string | null;
  consentPublicAt?: string | null;
  publicProfileVisible?: boolean;
  consentFormUploadedAt?: string | null;
  hasCriteriaDocument?: boolean;
  criteriaFileName?: string | null;
};

export type MyStageSubmissionSummary = {
  submissionId?: string | null;
  state?: string | null;
  uploadLocked?: boolean;
  receipt?: string | null;
};

export type MyStageOut = {
  stageId: string;
  order: number;
  name: string;
  type: string;
  opensAt?: string | null;
  closesAt?: string | null;
  exerciseAvailable: boolean;
  exerciseTitle?: string | null;
  exerciseStatus?: string | null;
  windowStatus: "upcoming" | "open" | "closed" | "unknown" | string;
  submission: MyStageSubmissionSummary;
};

export type MyStagesOut = {
  competitionId: string;
  competitionName: string;
  competitorId: string;
  skillId: string;
  skillName: string;
  stages: MyStageOut[];
};

export async function listMyRegistrations(): Promise<MyRegistrationOut[]> {
  return apiFetch<MyRegistrationOut[]>("/competitors/me/registrations");
}

export async function getMyStages(competitionId: string): Promise<MyStagesOut> {
  return apiFetch<MyStagesOut>(`/competitions/${competitionId}/me/stages`);
}

export type InstitutionRegistrationOut = {
  competitorId: string;
  competitorRef: string;
  competitionId: string;
  competitionName: string;
  competitionStatus: string;
  skillId: string;
  skillName: string;
  status: string;
  givenNames?: string | null;
  familyName?: string | null;
  gender?: string | null;
};

export type InstitutionCompetitionOut = {
  competitionId: string;
  name: string;
  status: string;
  period: { start: string; end: string };
  description?: string | null;
  window?: { opensAt: string; closesAt: string } | null;
};

export type NominationQuotaOut = {
  skillId: string;
  skillName: string;
  max: number;
  used: number;
  remaining: number;
  configured: boolean;
};

export type NominationQuotasOut = {
  competitionId: string;
  institutionId: string;
  quotas: NominationQuotaOut[];
};

export async function listInstitutionRegistrations(): Promise<
  InstitutionRegistrationOut[]
> {
  return apiFetch<InstitutionRegistrationOut[]>(
    "/institutions/me/registrations",
  );
}

export async function listInstitutionCompetitions(): Promise<
  InstitutionCompetitionOut[]
> {
  return apiFetch<InstitutionCompetitionOut[]>(
    "/institutions/me/competitions",
  );
}

export async function getNominationQuotas(
  competitionId: string,
): Promise<NominationQuotasOut> {
  return apiFetch<NominationQuotasOut>(
    `/competitions/${competitionId}/nomination-quotas`,
  );
}

export type NominationLimitSkillIn = {
  skillId: string;
  maxNominations: number;
};

export type InstitutionNominationLimitsUpsert = {
  zoneId: string;
  limits: NominationLimitSkillIn[];
};

export type InstitutionNominationLimitsOut = {
  competitionId: string;
  institutionId: string;
  zoneId: string | null;
  limits: NominationQuotaOut[];
};

export type InstitutionCompetitionMembershipOut = {
  institutionId: string;
  institutionName: string;
  institutionCode: string;
  zoneId: string;
  zoneName: string;
  configuredSkillCount: number;
};

export type CompetitionSchoolQuotasOut = {
  competitionId: string;
  quotas: NominationQuotaOut[];
};

export type CompetitionSchoolQuotasUpsert = {
  limits: NominationLimitSkillIn[];
};

export async function getCompetitionSchoolQuotas(
  competitionId: string,
): Promise<CompetitionSchoolQuotasOut> {
  return apiFetch<CompetitionSchoolQuotasOut>(
    `/admin/competitions/${competitionId}/school-quotas`,
  );
}

export async function upsertCompetitionSchoolQuotas(
  competitionId: string,
  payload: CompetitionSchoolQuotasUpsert,
): Promise<CompetitionSchoolQuotasOut> {
  return apiFetch<CompetitionSchoolQuotasOut>(
    `/admin/competitions/${competitionId}/school-quotas`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function getAdminInstitutionNominationLimits(
  competitionId: string,
  institutionId: string,
): Promise<InstitutionNominationLimitsOut> {
  return apiFetch<InstitutionNominationLimitsOut>(
    `/admin/competitions/${competitionId}/institutions/${institutionId}/nomination-limits`,
  );
}

export async function upsertInstitutionNominationLimits(
  competitionId: string,
  institutionId: string,
  payload: InstitutionNominationLimitsUpsert,
): Promise<InstitutionNominationLimitsOut> {
  return apiFetch<InstitutionNominationLimitsOut>(
    `/admin/competitions/${competitionId}/institutions/${institutionId}/nomination-limits`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function listCompetitionInstitutionMemberships(
  competitionId: string,
): Promise<InstitutionCompetitionMembershipOut[]> {
  return apiFetch<InstitutionCompetitionMembershipOut[]>(
    `/admin/competitions/${competitionId}/institution-memberships`,
  );
}

export async function getPublicCompetition(competitionId: string): Promise<PublicCompetitionOut> {
  return apiFetch<PublicCompetitionOut>(`/competitions/${competitionId}/public`, {
    skipAuthRetry: true,
  });
}

export async function updateCompetitionPublicProfile(
  competitionId: string,
  payload: { description: string | null },
): Promise<CompetitionOut> {
  return apiFetch<CompetitionOut>(`/competitions/${competitionId}/public-profile`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export type RegistrationWindowOut = {
  opensAt: string;
  closesAt: string;
};

export type RegistrationFormAdminOut = {
  fields: { name: string; type: string; required: boolean }[];
  maxSkills: number;
  photoMaxMb: number;
  photoFormats: string[];
  nationalIdPattern?: string | null;
  minorAgeUnder?: number | null;
  minorReferenceDate?: string | null;
};

export async function getRegistrationWindow(
  competitionId: string,
): Promise<RegistrationWindowOut | null> {
  return apiFetch<RegistrationWindowOut | null>(
    `/competitions/${competitionId}/registration-window`,
  );
}

export async function putRegistrationWindow(
  competitionId: string,
  payload: { opensAt: string; closesAt: string },
): Promise<RegistrationWindowOut> {
  return apiFetch<RegistrationWindowOut>(
    `/competitions/${competitionId}/registration-window`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function getRegistrationFormAdmin(
  competitionId: string,
): Promise<RegistrationFormAdminOut | null> {
  return apiFetch<RegistrationFormAdminOut | null>(
    `/competitions/${competitionId}/registration-form-admin`,
  );
}

export async function putRegistrationFormAdmin(
  competitionId: string,
  payload: { useDefaults?: boolean } & Partial<RegistrationFormAdminOut>,
): Promise<RegistrationFormAdminOut> {
  return apiFetch<RegistrationFormAdminOut>(
    `/competitions/${competitionId}/registration-form-admin`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function listAvailableSkills(
  competitionId: string,
): Promise<AvailableSkillOut[]> {
  return apiFetch<AvailableSkillOut[]>(`/competitions/${competitionId}/skills:available`);
}

export async function lookupInstitution(
  code: string,
): Promise<InstitutionLookupOut> {
  const qs = new URLSearchParams({ code: code.trim() });
  return apiFetch<InstitutionLookupOut>(`/institutions/lookup?${qs}`, {
    skipAuthRetry: true,
  });
}

export async function searchInstitutions(
  q: string,
  limit = 25,
): Promise<InstitutionLookupOut[]> {
  const qs = new URLSearchParams({
    q: q.trim(),
    limit: String(limit),
  });
  return apiFetch<InstitutionLookupOut[]>(`/institutions:search?${qs}`, {
    skipAuthRetry: true,
  });
}

export type ConsentRequestInput = {
  guardianName: string;
  guardianEmail: string;
  guardianPhone?: string | null;
};

export type ConsentRequestOut = {
  competitorId: string;
  status: string;
  expiresAt: string;
  token: string;
};

export type ConsentGrantInput = {
  scopes: string[];
  grantedBy?: string | null;
};

export type ConsentGrantOut = {
  competitorId: string;
  status: string;
  scopesGranted: string[];
  publicProfileVisible: boolean;
};

export type ConsentWithdrawOut = {
  competitorId: string;
  status: string;
  flags: string[];
  publicProfileVisible: boolean;
};

export async function requestConsent(
  competitorId: string,
  payload: ConsentRequestInput,
): Promise<ConsentRequestOut> {
  return apiFetch<ConsentRequestOut>(
    `/competitors/${competitorId}/consent-request`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function grantConsent(
  token: string,
  payload: ConsentGrantInput,
): Promise<ConsentGrantOut> {
  return apiFetch<ConsentGrantOut>(`/consent/${token}:grant`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function withdrawConsent(
  competitorId: string,
): Promise<ConsentWithdrawOut> {
  return apiFetch<ConsentWithdrawOut>(
    `/competitors/${competitorId}/consent:withdraw`,
    { method: "POST" },
  );
}

export type ConsentFormUploadOut = {
  competitorId: string;
  status: string;
  scopesGranted: string[];
  publicProfileVisible: boolean;
  consentFormUploadedAt: string;
  sha256: string;
};

export async function downloadConsentForm(
  competitorId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitors/${competitorId}/consent-form.pdf`,
  );
  return {
    blob,
    filename: filename ?? `guardian-consent-${competitorId}.pdf`,
  };
}

export async function downloadUploadedConsentForm(
  competitorId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitors/${competitorId}/consent-form/signed.pdf?download=true`,
  );
  return {
    blob,
    filename: filename ?? `signed-consent-${competitorId}.pdf`,
  };
}

export async function fetchUploadedConsentForm(
  competitorId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/competitors/${competitorId}/consent-form/signed.pdf`,
  );
  return {
    blob,
    filename: filename ?? `signed-consent-${competitorId}.pdf`,
  };
}

export async function uploadSignedConsentForm(
  competitorId: string,
  file: File,
  scopes: string[],
  grantedBy?: string | null,
): Promise<ConsentFormUploadOut> {
  const body = new FormData();
  body.append("file", file);
  for (const scope of scopes) {
    body.append("scopes", scope);
  }
  if (grantedBy?.trim()) {
    body.append("grantedBy", grantedBy.trim());
  }
  return apiFetch<ConsentFormUploadOut>(
    `/competitors/${competitorId}/consent-form`,
    {
      method: "POST",
      body,
    },
  );
}

export type EligibilityScreenOut = {
  competitorId: string;
  eligible: boolean;
  status: string;
  failedRules: string[];
  category?: string | null;
  ageAtReference?: number | null;
};

export type EligibilityOverrideInput = {
  value: boolean;
  reason: string;
  category?: string | null;
};

export type EligibilityOverrideOut = {
  competitorId: string;
  eligible: boolean;
  status: string;
  reason: string;
  category?: string | null;
};

export type AdminCompetitorItem = {
  competitorId: string;
  refNo: string;
  givenNames?: string | null;
  familyName?: string | null;
  skillId: string;
  skillName: string;
  institutionId?: string | null;
  institutionName?: string | null;
  status: string;
  eligibilityStatus?: string | null;
  zoneId?: string | null;
  zoneName?: string | null;
  consentFormUploadedAt?: string | null;
  consentVerificationStatus?: string | null;
};

export type ConsentVerifyOut = {
  competitorId: string;
  consentVerificationStatus: string;
  consentVerifiedAt?: string | null;
  consentVerificationReason?: string | null;
};

export async function listAdminCompetitors(
  competitionId: string,
  options?: { skillId?: string | null; q?: string | null; status?: string | null },
): Promise<AdminCompetitorItem[]> {
  const params = new URLSearchParams();
  if (options?.skillId) params.set("skillId", options.skillId);
  if (options?.q) params.set("q", options.q);
  if (options?.status) params.set("status", options.status);
  const qs = params.toString();
  return apiFetch<AdminCompetitorItem[]>(
    `/competitions/${competitionId}/competitors${qs ? `?${qs}` : ""}`,
  );
}

export async function fetchAdminUploadedConsentForm(
  competitorId: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiFetchBlob(
    `/admin/competitors/${competitorId}/consent-form/signed.pdf`,
  );
  return {
    blob,
    filename: filename ?? `signed-consent-${competitorId}.pdf`,
  };
}

export async function verifyConsentForm(
  competitorId: string,
  payload: { outcome: "VERIFIED" | "REJECTED"; reason?: string | null },
): Promise<ConsentVerifyOut> {
  return apiFetch<ConsentVerifyOut>(
    `/admin/competitors/${competitorId}/consent:verify`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function screenCompetitor(
  competitorId: string,
): Promise<EligibilityScreenOut> {
  return apiFetch<EligibilityScreenOut>(
    `/competitors/${competitorId}:screen`,
    { method: "POST" },
  );
}

export async function overrideEligibility(
  competitorId: string,
  payload: EligibilityOverrideInput,
): Promise<EligibilityOverrideOut> {
  return apiFetch<EligibilityOverrideOut>(
    `/competitors/${competitorId}/eligibility:override`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type SubmissionOut = {
  submissionId: string;
  competitionId: string;
  stageId?: string | null;
  competitorId: string;
  state: string;
  deadlineAt?: string | null;
  timedExpiresAt?: string | null;
  uploadLocked: boolean;
  late: boolean;
  hash?: string | null;
  receipt?: string | null;
  submittedAt?: string | null;
};

export type ArtefactUploadOut = {
  artefactId: string;
  uploadId?: string | null;
  scan: string;
  receivedBytes?: number | null;
  complete: boolean;
  quarantined: boolean;
};

export type ArtefactSessionOut = {
  uploadId: string;
  artefactId: string;
  receivedBytes: number;
  totalSize: number;
};

export type ArtefactSessionCreate = {
  deliverableCode: string;
  filename: string;
  contentType?: string | null;
  totalSize: number;
};

export type FinaliseOut = {
  state: string;
  hash?: string | null;
  receipt?: string | null;
  late: boolean;
};

/** Files at or above this size use resumable chunked upload. */
export const SUBMISSION_RESUMABLE_THRESHOLD_BYTES = 256 * 1024;
export const SUBMISSION_CHUNK_SIZE_BYTES = 256 * 1024;

export async function openSubmission(
  competitionId: string,
  stageId: string,
): Promise<SubmissionOut> {
  return apiFetch<SubmissionOut>(
    `/competitions/${competitionId}/stages/${stageId}/submissions`,
    { method: "POST" },
  );
}

export async function uploadArtefact(
  submissionId: string,
  options: {
    deliverableCode: string;
    filename: string;
    contentType?: string | null;
    data: Blob | ArrayBuffer;
  },
): Promise<ArtefactUploadOut> {
  const headers: Record<string, string> = {
    "X-Deliverable-Code": options.deliverableCode,
    "X-Filename": options.filename,
    "Content-Type":
      options.contentType ||
      (options.data instanceof Blob && options.data.type
        ? options.data.type
        : "application/octet-stream"),
  };
  if (options.contentType) {
    headers["X-Content-Type"] = options.contentType;
  }
  return apiFetch<ArtefactUploadOut>(
    `/submissions/${submissionId}/artefacts`,
    {
      method: "POST",
      headers,
      body: options.data,
    },
  );
}

export async function initArtefactSession(
  submissionId: string,
  payload: ArtefactSessionCreate,
): Promise<ArtefactSessionOut> {
  return apiFetch<ArtefactSessionOut>(
    `/submissions/${submissionId}/artefacts/sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function appendArtefactChunk(
  submissionId: string,
  uploadId: string,
  options: {
    data: Blob | ArrayBuffer;
    start: number;
    endInclusive: number;
    totalSize: number;
  },
): Promise<ArtefactUploadOut> {
  return apiFetch<ArtefactUploadOut>(
    `/submissions/${submissionId}/artefacts/sessions/${uploadId}`,
    {
      method: "PUT",
      headers: {
        "Content-Range": `bytes ${options.start}-${options.endInclusive}/${options.totalSize}`,
        "Content-Type": "application/octet-stream",
      },
      body: options.data,
    },
  );
}

export async function uploadArtefactResumable(
  submissionId: string,
  options: {
    deliverableCode: string;
    file: File;
    chunkSize?: number;
    onProgress?: (receivedBytes: number, totalSize: number) => void;
  },
): Promise<ArtefactUploadOut> {
  const chunkSize = options.chunkSize ?? SUBMISSION_CHUNK_SIZE_BYTES;
  const totalSize = options.file.size;
  const session = await initArtefactSession(submissionId, {
    deliverableCode: options.deliverableCode,
    filename: options.file.name,
    contentType: options.file.type || null,
    totalSize,
  });

  let offset = session.receivedBytes;
  options.onProgress?.(offset, totalSize);
  let last: ArtefactUploadOut = {
    artefactId: session.artefactId,
    uploadId: session.uploadId,
    scan: "PENDING",
    receivedBytes: offset,
    complete: false,
    quarantined: false,
  };

  while (offset < totalSize) {
    const end = Math.min(offset + chunkSize, totalSize);
    const chunk = options.file.slice(offset, end);
    last = await appendArtefactChunk(submissionId, session.uploadId, {
      data: chunk,
      start: offset,
      endInclusive: end - 1,
      totalSize,
    });
    offset = last.receivedBytes ?? end;
    options.onProgress?.(offset, totalSize);
    if (last.complete) break;
  }

  return last;
}

export async function finaliseSubmission(
  submissionId: string,
): Promise<FinaliseOut> {
  return apiFetch<FinaliseOut>(`/submissions/${submissionId}:finalise`, {
    method: "POST",
  });
}

export async function expireSubmissionTimer(
  submissionId: string,
): Promise<FinaliseOut> {
  return apiFetch<FinaliseOut>(`/submissions/${submissionId}:expire-timer`, {
    method: "POST",
  });
}

export type QueueSubmissionOut = {
  submissionId: string;
  competitorId?: string | null;
  anonCode?: string | null;
  state: string;
};

export type AssessorQueueOut = {
  submissions: QueueSubmissionOut[];
  items?: QueueSubmissionOut[] | null;
};

export type MyAssignmentOut = {
  assignmentId: string;
  competitionId: string;
  competitionName: string;
  skillId: string;
  skillName: string;
  zoneId: string;
  zoneName: string;
};

export type CriterionMarkIn = {
  criterionId: string;
  type: string;
  value: number;
  judgeId?: string | null;
  comment?: string | null;
};

export type PenaltyIn = {
  code: string;
  deduction?: number | null;
};

export type ScorePutInput = {
  criterionMarks: CriterionMarkIn[];
  penalties?: PenaltyIn[];
  finalize?: boolean;
};

export type ScoreMarkOut = {
  criterionId: string;
  type: string;
  value?: number | null;
  assessorId: string;
  judgeId?: string | null;
  comment?: string | null;
  status: string;
};

export type PenaltyOut = {
  code: string;
  deduction: number;
};

export type ScorePutOut = {
  total: number;
  status: string;
  breakdown: {
    marks: ScoreMarkOut[];
    penalties: PenaltyOut[];
    total: number;
  };
};

export type AssessmentCriterion = {
  criterionId?: string;
  id?: string;
  type?: string;
  max?: number;
  maxMark?: number;
  label?: string;
  [key: string]: unknown;
};

export type AssessmentViewOut = {
  submissionId: string;
  anonCode: string;
  state: string;
  blindMode: boolean;
  competitorId?: string | null;
  givenNames?: string | null;
  familyName?: string | null;
  institutionId?: string | null;
  photoKey?: string | null;
  criteria: AssessmentCriterion[];
  penalties: { code?: string; deduction?: number; [key: string]: unknown }[];
  myMarks: ScoreMarkOut[];
  total?: number | null;
};

export type ModerationFlagOut = {
  criterionId: string;
  spread?: number | null;
  rawMarks: number[];
  flagged: boolean;
  state: string;
  standardisedValue?: number | null;
  method?: string | null;
  reason?: string | null;
};

export type ModerationAnalyseOut = {
  submissionId: string;
  tolerance: number;
  flags: ModerationFlagOut[];
};

export type ModerationApplyInput = {
  criterionId: string;
  method: "STANDARDISE" | "MANUAL" | "SELECT_ASSESSOR" | string;
  value?: number | null;
  assessorId?: string | null;
  reason?: string | null;
};

export type ModerationApplyOut = {
  submissionId: string;
  criterionId: string;
  method: string;
  standardisedValue: number;
  rawMarks: number[];
  total: number;
  reason?: string | null;
};

export type AssessorTotalOut = {
  assessorId: string;
  assessorName?: string | null;
  assessorEmail?: string | null;
  total: number;
  markCount: number;
  finalized?: boolean;
};

export type ScoringListItemOut = {
  submissionId: string;
  anonCode?: string | null;
  state: string;
  skillId?: string | null;
  skillName?: string | null;
  stageId?: string | null;
  stageName?: string | null;
  exerciseTitle?: string | null;
  competitorId?: string | null;
  competitorRef?: string | null;
  competitorName?: string | null;
  blindMode: boolean;
  submissionTotal?: number | null;
  assessorCount: number;
  assessorTotals: AssessorTotalOut[];
  disagreement: boolean;
  openFlags: number;
  resultsReleased: boolean;
};

export type CriterionAssessorMarkOut = {
  assessorId: string;
  assessorName?: string | null;
  type: string;
  raw?: number | null;
  standardised?: number | null;
  status: string;
  comment?: string | null;
};

export type CriterionScoringOut = {
  criterionId: string;
  name: string;
  type: string;
  max?: number | null;
  marks: CriterionAssessorMarkOut[];
  standardisedValue?: number | null;
  disagreement: boolean;
};

export type ScoringDetailOut = {
  submissionId: string;
  anonCode?: string | null;
  state: string;
  skillId?: string | null;
  skillName?: string | null;
  stageId?: string | null;
  stageName?: string | null;
  exerciseTitle?: string | null;
  blindMode: boolean;
  competitorId?: string | null;
  competitorRef?: string | null;
  competitorName?: string | null;
  submissionTotal?: number | null;
  assessorTotals: AssessorTotalOut[];
  criteria: CriterionScoringOut[];
  disagreement: boolean;
  openFlags: number;
  resultsReleased: boolean;
};

export type ResolveTotalOut = {
  submissionId: string;
  method: string;
  assessorId?: string | null;
  total: number;
  assessorTotals: AssessorTotalOut[];
  reason?: string | null;
};

export async function listMyAssignments(): Promise<MyAssignmentOut[]> {
  return apiFetch<MyAssignmentOut[]>("/assessors/me/assignments");
}

export async function fetchAssessorQueue(
  expertId: string,
  competitionId: string,
): Promise<AssessorQueueOut> {
  return apiFetch<AssessorQueueOut>(
    `/assessors/${expertId}/queue?competitionId=${encodeURIComponent(competitionId)}`,
  );
}

export async function fetchAssessment(
  submissionId: string,
): Promise<AssessmentViewOut> {
  return apiFetch<AssessmentViewOut>(
    `/submissions/${submissionId}/assessment`,
  );
}

export async function putScores(
  submissionId: string,
  payload: ScorePutInput,
): Promise<ScorePutOut> {
  return apiFetch<ScorePutOut>(`/submissions/${submissionId}/scores`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function analyseModeration(
  submissionId: string,
): Promise<ModerationAnalyseOut> {
  return apiFetch<ModerationAnalyseOut>(
    `/submissions/${submissionId}/moderation:analyse`,
    { method: "POST" },
  );
}

export async function applyModeration(
  submissionId: string,
  payload: ModerationApplyInput,
): Promise<ModerationApplyOut> {
  return apiFetch<ModerationApplyOut>(
    `/submissions/${submissionId}/moderation`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function listScoringOverview(
  competitionId: string,
  options?: { skillId?: string | null; stageId?: string | null },
): Promise<ScoringListItemOut[]> {
  const params = new URLSearchParams();
  if (options?.skillId) params.set("skillId", options.skillId);
  if (options?.stageId) params.set("stageId", options.stageId);
  const q = params.toString();
  return apiFetch<ScoringListItemOut[]>(
    `/competitions/${competitionId}/scoring${q ? `?${q}` : ""}`,
  );
}

export async function fetchScoringDetail(
  submissionId: string,
): Promise<ScoringDetailOut> {
  return apiFetch<ScoringDetailOut>(`/submissions/${submissionId}/scoring`);
}

export async function resolveSubmissionTotal(
  submissionId: string,
  payload: {
    method: "AVERAGE" | "SELECT_ASSESSOR";
    assessorId?: string | null;
    reason?: string | null;
  },
): Promise<ResolveTotalOut> {
  return apiFetch<ResolveTotalOut>(
    `/submissions/${submissionId}/scoring:resolve-total`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type ShortlistRankedItem = {
  competitorId: string;
  zoneId: string;
  score: number;
  rank: number;
  outcome: string;
  reason?: string | null;
  refNo?: string | null;
};

export type ShortlistGenerateOut = {
  shortlistId: string;
  stageId: string;
  state: string;
  isFinalStage: boolean;
  selectionMode: string;
  byZone?: Record<string, ShortlistRankedItem[]> | null;
  national?: ShortlistRankedItem[] | null;
  generatedAt: string;
};

export type ShortlistConfirmOut = {
  shortlistId: string;
  state: string;
  advanced: string[];
  waitlist: string[];
  excluded?: string[];
  finalists?: ShortlistRankedItem[] | null;
  notified?: number;
};

export async function generateShortlist(
  competitionId: string,
  stageId: string,
): Promise<ShortlistGenerateOut> {
  return apiFetch<ShortlistGenerateOut>(
    `/competitions/${competitionId}/stages/${stageId}:shortlist`,
    { method: "POST" },
  );
}

export async function confirmShortlist(
  competitionId: string,
  stageId: string,
): Promise<ShortlistConfirmOut> {
  return apiFetch<ShortlistConfirmOut>(
    `/competitions/${competitionId}/stages/${stageId}:confirm-shortlist`,
    { method: "POST" },
  );
}

export type PrepareResultsOut = {
  publicationId: string;
  state: string;
  skillId?: string | null;
  stageId?: string | null;
  entryCount: number;
  releaseAt: string;
};

export type ReleaseResultsOut = {
  publicationId: string;
  releasedAt: string;
  state: string;
  certificateCount: number;
};

export type CorrectResultOut = {
  resultId: string;
  version: number;
  publicationId: string;
  outcome: string;
  certificateId?: string | null;
};

export type PublicResultItem = {
  resultId: string;
  competitorId: string;
  skillId: string;
  outcome: string;
  score?: number | null;
  rank?: number | null;
  certificateId?: string | null;
  refNo?: string | null;
};

export type PublicResultsOut = {
  state: string;
  status?: string | null;
  releasedAt?: string | null;
  results: PublicResultItem[];
};

export type CompetitorResultsOut = {
  state: string;
  status?: string | null;
  result?: PublicResultItem | null;
  certificate?: string | null;
};

export type AdminResultItem = {
  resultId: string;
  publicationId: string;
  competitionId: string;
  skillId: string;
  skillName: string;
  stageId?: string | null;
  stageName?: string | null;
  competitorId: string;
  competitorRef?: string | null;
  competitorName?: string | null;
  outcome: string;
  score?: number | null;
  rank?: number | null;
  version: number;
  publicationState: string;
  releaseAt: string;
  releasedAt?: string | null;
};

export type ResultsConfigOut = {
  competitionId: string;
  releaseAt: string;
  audience: string[];
  neutralStatus: string;
  awardByRank: Record<string, string>;
  defaultOutcome: string;
  configured: boolean;
};

export type ResultsConfigPutInput = {
  releaseAt: string;
  audience: string[];
  neutralStatus?: string;
  awardByRank?: Record<string, string>;
  defaultOutcome?: string;
  ensureTemplates?: boolean;
};

export async function getResultsConfig(
  competitionId: string,
): Promise<ResultsConfigOut> {
  return apiFetch<ResultsConfigOut>(
    `/competitions/${competitionId}/results-config`,
  );
}

export async function putResultsConfig(
  competitionId: string,
  payload: ResultsConfigPutInput,
): Promise<ResultsConfigOut> {
  return apiFetch<ResultsConfigOut>(
    `/competitions/${competitionId}/results-config`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function prepareResults(
  competitionId: string,
  options?: { skillId?: string | null; stageId?: string | null },
): Promise<PrepareResultsOut> {
  return apiFetch<PrepareResultsOut>(`/competitions/${competitionId}/results:prepare`, {
    method: "POST",
    body: JSON.stringify({
      skillId: options?.skillId || null,
      stageId: options?.stageId || null,
    }),
  });
}

export async function releaseResults(
  competitionId: string,
  options?: {
    manual?: boolean;
    skillId?: string | null;
    stageId?: string | null;
  },
): Promise<ReleaseResultsOut> {
  return apiFetch<ReleaseResultsOut>(`/competitions/${competitionId}/results:release`, {
    method: "POST",
    body: JSON.stringify({
      manual: options?.manual ?? true,
      skillId: options?.skillId ?? null,
      stageId: options?.stageId ?? null,
    }),
  });
}

export async function correctResult(
  resultId: string,
  payload: { changes: Record<string, unknown>; reason: string },
): Promise<CorrectResultOut> {
  return apiFetch<CorrectResultOut>(`/results/${resultId}:correct`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listAdminResults(
  competitionId: string,
  options?: { skillId?: string | null; q?: string | null; state?: string | null },
): Promise<AdminResultItem[]> {
  const params = new URLSearchParams();
  if (options?.skillId) params.set("skillId", options.skillId);
  if (options?.q) params.set("q", options.q);
  if (options?.state) params.set("state", options.state);
  const q = params.toString();
  return apiFetch<AdminResultItem[]>(
    `/competitions/${competitionId}/results${q ? `?${q}` : ""}`,
  );
}

export async function fetchPublicResults(
  competitionId: string,
): Promise<PublicResultsOut> {
  return apiFetch<PublicResultsOut>(`/public/competitions/${competitionId}/results`);
}

export async function fetchMyResults(
  competitionId: string,
): Promise<CompetitorResultsOut> {
  return apiFetch<CompetitorResultsOut>(`/competitions/${competitionId}/results/me`);
}

export type WithdrawOut = {
  competitorId: string;
  status: string;
  promotedCompetitorId?: string | null;
};

export type SubstituteReplacement = {
  refNo: string;
  givenNames: string;
  familyName: string;
  dateOfBirth: string;
  nationality?: string | null;
  enrolmentAttested?: boolean;
  email?: string | null;
  mobile?: string | null;
};

export type SubstituteOut = {
  withdrawnCompetitorId: string;
  replacementCompetitorId: string;
  eligible: boolean;
  status: string;
  failedRules: string[];
};

export async function withdrawCompetitor(
  competitorId: string,
  reason: string,
): Promise<WithdrawOut> {
  return apiFetch<WithdrawOut>(`/competitors/${competitorId}:withdraw`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function substituteCompetitor(
  competitorId: string,
  replacement: SubstituteReplacement,
): Promise<SubstituteOut> {
  return apiFetch<SubstituteOut>(`/competitors/${competitorId}:substitute`, {
    method: "POST",
    body: JSON.stringify({ replacement }),
  });
}

export type AppealOut = {
  appealId: string;
  competitionId: string;
  competitorId: string;
  stageId: string;
  state: string;
  reason: string;
  officerId?: string | null;
  rulingOutcome?: string | null;
  rulingReason?: string | null;
  remedy?: string | null;
};

export type AppealListItem = {
  appealId: string;
  competitionId: string;
  competitorId: string;
  competitorRef?: string | null;
  competitorName?: string | null;
  stageId: string;
  stageName?: string | null;
  skillId?: string | null;
  skillName?: string | null;
  state: string;
  reason: string;
  officerId?: string | null;
  rulingOutcome?: string | null;
  rulingReason?: string | null;
  remedy?: string | null;
  submittedAt?: string | null;
};

export type DisqualifyOut = {
  competitorId: string;
  status: string;
  reason: string;
  promotedCompetitorId?: string | null;
};

export async function listAppeals(
  competitionId: string,
  options?: { skillId?: string | null; q?: string | null; state?: string | null },
): Promise<AppealListItem[]> {
  const params = new URLSearchParams();
  if (options?.skillId) params.set("skillId", options.skillId);
  if (options?.q) params.set("q", options.q);
  if (options?.state) params.set("state", options.state);
  const q = params.toString();
  return apiFetch<AppealListItem[]>(
    `/competitions/${competitionId}/appeals${q ? `?${q}` : ""}`,
  );
}

export async function lodgeAppeal(
  competitionId: string,
  payload: { competitorId: string; stageId: string; reason: string },
): Promise<AppealOut> {
  return apiFetch<AppealOut>(`/competitions/${competitionId}/appeals`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function assignAppeal(
  appealId: string,
  officerId: string,
): Promise<AppealOut> {
  return apiFetch<AppealOut>(`/appeals/${appealId}:assign`, {
    method: "POST",
    body: JSON.stringify({ officerId }),
  });
}

export async function ruleAppeal(
  appealId: string,
  payload: { outcome: string; reason?: string | null; remedy?: string | null },
): Promise<AppealOut> {
  return apiFetch<AppealOut>(`/appeals/${appealId}:rule`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function disqualifyCompetitor(
  competitorId: string,
  reason: string,
): Promise<DisqualifyOut> {
  return apiFetch<DisqualifyOut>(`/competitors/${competitorId}:disqualify`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export type ScheduleSessionOut = {
  sessionId: string;
  competitionId: string;
  venueId: string;
  startsAt: string;
  endsAt: string;
  workstations: number;
  state: string;
};

export type ScheduleSessionListItem = {
  sessionId: string;
  competitionId: string;
  venueId: string;
  venueName: string;
  startsAt: string;
  endsAt: string;
  workstations: number;
  state: string;
  assignmentCount: number;
  incidentCount: number;
};

export type VenueOut = {
  venueId: string;
  competitionId: string;
  name: string;
  capacity: number;
  workstations: number;
  active: boolean;
  zoneId?: string | null;
};

export type ScheduleAssignmentDetail = {
  assignmentId: string;
  sessionId: string;
  competitorId: string;
  competitorRef?: string | null;
  competitorName?: string | null;
  skillId?: string | null;
  skillName?: string | null;
  workstation: string;
  readiness: string;
};

export type ScheduleSessionDetail = {
  sessionId: string;
  competitionId: string;
  venueId: string;
  venueName: string;
  startsAt: string;
  endsAt: string;
  workstations: number;
  state: string;
  assignments: ScheduleAssignmentDetail[];
  incidents: ScheduleIncidentOut[];
};

export type ScheduleAssignmentOut = {
  assignmentId: string;
  sessionId: string;
  competitorId: string;
  workstation: string;
  readiness: string;
};

export type ScheduleIncidentOut = {
  incidentId: string;
  sessionId: string;
  competitionId: string;
  summary: string;
  severity?: string | null;
  recordedAt: string;
};

export async function listVenues(competitionId: string): Promise<VenueOut[]> {
  return apiFetch<VenueOut[]>(`/competitions/${competitionId}/venues`);
}

export async function listScheduleSessions(
  competitionId: string,
  options?: { skillId?: string | null; q?: string | null },
): Promise<ScheduleSessionListItem[]> {
  const params = new URLSearchParams();
  if (options?.skillId) params.set("skillId", options.skillId);
  if (options?.q) params.set("q", options.q);
  const q = params.toString();
  return apiFetch<ScheduleSessionListItem[]>(
    `/competitions/${competitionId}/schedule/sessions${q ? `?${q}` : ""}`,
  );
}

export async function getScheduleSession(
  sessionId: string,
): Promise<ScheduleSessionDetail> {
  return apiFetch<ScheduleSessionDetail>(`/schedule/sessions/${sessionId}`);
}

export async function createScheduleSession(
  competitionId: string,
  payload: {
    venueId: string;
    startsAt: string;
    endsAt: string;
    workstations: number;
  },
): Promise<ScheduleSessionOut> {
  return apiFetch<ScheduleSessionOut>(
    `/competitions/${competitionId}/schedule/sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function assignScheduleSlot(
  sessionId: string,
  payload: { competitorId: string; workstation: string },
): Promise<ScheduleAssignmentOut> {
  return apiFetch<ScheduleAssignmentOut>(
    `/schedule/sessions/${sessionId}/assignments`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function recordScheduleIncident(
  sessionId: string,
  payload: { summary: string; severity?: string | null },
): Promise<ScheduleIncidentOut> {
  return apiFetch<ScheduleIncidentOut>(
    `/schedule/sessions/${sessionId}/incidents`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export type PublicCompetitorListItem = {
  competitorId: string;
  displayName?: string | null;
  photo?: string | null;
  institution?: string | null;
  skill?: string | null;
  stageStatus?: string | null;
  zone?: string | null;
};

export type PublicCompetitorDirectoryOut = {
  items: PublicCompetitorListItem[];
  nextCursor?: string | null;
};

export type PublicCompetitorProfileOut = {
  competitorId: string;
  public?: boolean;
  competitorRef?: string | null;
  displayName?: string | null;
  photo?: string | null;
  institution?: string | null;
  skill?: string | null;
  stageStatus?: string | null;
  zone?: string | null;
};

export async function fetchPublicDirectory(
  competitionId: string,
  options?: {
    skill?: string | null;
    zone?: string | null;
    cursor?: string | null;
    limit?: number | null;
  },
): Promise<PublicCompetitorDirectoryOut> {
  const params = new URLSearchParams();
  if (options?.skill) params.set("skill", options.skill);
  if (options?.zone) params.set("zone", options.zone);
  if (options?.cursor) params.set("cursor", options.cursor);
  if (options?.limit) params.set("limit", String(options.limit));
  const qs = params.toString();
  return apiFetch<PublicCompetitorDirectoryOut>(
    `/public/competitions/${competitionId}/competitors${qs ? `?${qs}` : ""}`,
  );
}

export async function fetchPublicCompetitorProfile(
  competitorKey: string,
): Promise<PublicCompetitorProfileOut> {
  return apiFetch<PublicCompetitorProfileOut>(
    `/public/competitors/${encodeURIComponent(competitorKey)}`,
  );
}

export type ProgressionCounts = {
  advanced: number;
  waitlisted: number;
  excluded: number;
};

export type ProgressionStageOut = {
  stageId: string;
  stage: string;
  order: number;
  status: string;
  counts?: ProgressionCounts | null;
};

export type ProgressionZoneOut = {
  zoneId: string;
  zoneName: string;
  stages: ProgressionStageOut[];
};

export type SkillProgressionOut = {
  skillId: string;
  skillName: string;
  byZone: ProgressionZoneOut[];
};

export async function fetchSkillProgression(
  competitionId: string,
  skillId: string,
): Promise<SkillProgressionOut> {
  return apiFetch<SkillProgressionOut>(
    `/public/competitions/${competitionId}/skills/${skillId}/progression`,
  );
}

export type AuditEventOut = {
  eventId: string;
  competitionId?: string | null;
  actorId?: string | null;
  actorRole?: string | null;
  action: string;
  entityType: string;
  entityId: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string | null;
  timestamp: string;
  signatureValid?: boolean | null;
};

export type AuditListOut = {
  events: AuditEventOut[];
};

export type DsarJobOut = {
  jobId: string;
  status: string;
  requestType?: string | null;
  export?: Record<string, unknown> | null;
  resultSummary?: string | null;
  completedAt?: string | null;
};

export async function fetchAuditLog(options?: {
  entity?: string | null;
  actor?: string | null;
  from?: string | null;
  to?: string | null;
  limit?: number;
}): Promise<AuditListOut> {
  const params = new URLSearchParams();
  if (options?.entity) params.set("entity", options.entity);
  if (options?.actor) params.set("actor", options.actor);
  if (options?.from) params.set("from", options.from);
  if (options?.to) params.set("to", options.to);
  if (options?.limit) params.set("limit", String(options.limit));
  const qs = params.toString();
  return apiFetch<AuditListOut>(`/admin/audit${qs ? `?${qs}` : ""}`);
}

export async function createDsar(payload: {
  subjectId: string;
  type: "ACCESS" | "ERASURE" | "WITHDRAW" | string;
}): Promise<DsarJobOut> {
  return apiFetch<DsarJobOut>("/governance/dsar", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchDsarJob(jobId: string): Promise<DsarJobOut> {
  return apiFetch<DsarJobOut>(`/governance/dsar/${jobId}`);
}

export async function login(email: string, password: string): Promise<Me> {
  const tokens = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuthRetry: true,
  });
  setTokens(tokens.access_token, tokens.refresh_token);
  const me = await apiFetch<Me & { mustChangePassword?: boolean }>("/auth/me");
  const mustChange = Boolean(
    me.must_change_password ??
      me.mustChangePassword ??
      tokens.must_change_password,
  );
  return { ...me, must_change_password: mustChange };
}

export type RegisterAccountInput = {
  email: string;
  fullName: string;
  password: string;
  passwordConfirm: string;
  captchaToken?: string | null;
};

export async function registerAccount(
  payload: RegisterAccountInput,
): Promise<Me> {
  const tokens = await apiFetch<TokenResponse & { user?: unknown }>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify({
        email: payload.email,
        fullName: payload.fullName,
        password: payload.password,
        passwordConfirm: payload.passwordConfirm,
        captchaToken: payload.captchaToken ?? "ok",
      }),
      skipAuthRetry: true,
    },
  );
  setTokens(tokens.access_token, tokens.refresh_token);
  const me = await apiFetch<Me & { mustChangePassword?: boolean }>("/auth/me");
  const mustChange = Boolean(
    me.must_change_password ??
      me.mustChangePassword ??
      tokens.must_change_password,
  );
  return { ...me, must_change_password: mustChange };
}

export type RegisterInstitutionInput = RegisterAccountInput & {
  schoolCode: string;
};

export async function registerInstitution(
  payload: RegisterInstitutionInput,
): Promise<Me> {
  const tokens = await apiFetch<TokenResponse & { user?: unknown }>(
    "/auth/register-institution",
    {
      method: "POST",
      body: JSON.stringify({
        email: payload.email,
        fullName: payload.fullName,
        password: payload.password,
        passwordConfirm: payload.passwordConfirm,
        schoolCode: payload.schoolCode,
        captchaToken: payload.captchaToken ?? "ok",
      }),
      skipAuthRetry: true,
    },
  );
  setTokens(tokens.access_token, tokens.refresh_token);
  const me = await apiFetch<Me & { mustChangePassword?: boolean }>("/auth/me");
  const mustChange = Boolean(
    me.must_change_password ??
      me.mustChangePassword ??
      tokens.must_change_password,
  );
  return { ...me, must_change_password: mustChange };
}

export async function acceptInvite(payload: {
  token: string;
  password: string;
  passwordConfirm: string;
}): Promise<void> {
  await apiFetch<void>("/auth/accept-invite", {
    method: "POST",
    body: JSON.stringify({
      token: payload.token,
      password: payload.password,
      passwordConfirm: payload.passwordConfirm,
    }),
    skipAuthRetry: true,
  });
}

export async function changePassword(payload: {
  currentPassword: string;
  newPassword: string;
  newPasswordConfirm: string;
}): Promise<void> {
  await apiFetch<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      currentPassword: payload.currentPassword,
      newPassword: payload.newPassword,
      newPasswordConfirm: payload.newPasswordConfirm,
    }),
  });
}

export async function listUsers(params?: {
  role?: string;
  active?: boolean;
  q?: string;
}): Promise<UserOut[]> {
  const search = new URLSearchParams();
  if (params?.role) search.set("role", params.role);
  if (params?.active !== undefined) search.set("active", String(params.active));
  if (params?.q) search.set("q", params.q);
  const qs = search.toString();
  return apiFetch<UserOut[]>(`/users${qs ? `?${qs}` : ""}`);
}

export async function createUser(payload: {
  email: string;
  fullName: string;
  role: string;
  institutionId?: string;
  credentialMode: "TEMP_PASSWORD" | "INVITE";
  temporaryPassword?: string;
}): Promise<CreateUserResponse> {
  return apiFetch<CreateUserResponse>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function patchUser(
  userId: string,
  payload: {
    fullName?: string;
    institutionId?: string | null;
    isActive?: boolean;
  },
): Promise<UserOut> {
  return apiFetch<UserOut>(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listInstitutions(params?: {
  q?: string;
  active?: boolean;
  regionId?: string;
}): Promise<InstitutionOut[]> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.active !== undefined) search.set("active", String(params.active));
  if (params?.regionId) search.set("regionId", params.regionId);
  const qs = search.toString();
  return apiFetch<InstitutionOut[]>(`/institutions${qs ? `?${qs}` : ""}`);
}

export async function createInstitution(
  payload: InstitutionCreateInput,
): Promise<InstitutionOut> {
  return apiFetch<InstitutionOut>("/institutions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function patchInstitution(
  institutionId: string,
  payload: InstitutionPatchInput,
): Promise<InstitutionOut> {
  return apiFetch<InstitutionOut>(`/institutions/${institutionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function downloadInstitutionsImportTemplate(): Promise<{
  blob: Blob;
  filename: string;
}> {
  const { blob, filename } = await apiFetchBlob(
    "/institutions/import-template",
  );
  return {
    blob,
    filename: filename || "institutions-import-template.xlsx",
  };
}

export async function importInstitutions(
  file: File,
): Promise<InstitutionImportResult> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<InstitutionImportResult>("/institutions:import", {
    method: "POST",
    body,
  });
}

export async function fetchMe(): Promise<Me> {
  return apiFetch<Me>("/auth/me");
}

export function logout(): void {
  clearTokens();
}

export function isAdminRole(role: string): boolean {
  return role === "ADMIN" || role === "SUPER_ADMIN";
}

export function isSuperAdminRole(role: string): boolean {
  return role === "SUPER_ADMIN";
}

export function isInstitutionRole(role: string): boolean {
  return role === "INSTITUTION";
}

export function isCompetitorRole(role: string): boolean {
  return role === "COMPETITOR";
}

export function isExpertRole(role: string): boolean {
  return role === "EXPERT" || role === "CHIEF_EXPERT";
}

export function isChiefExpertRole(role: string): boolean {
  return role === "CHIEF_EXPERT";
}

export type AppRole =
  | "admin"
  | "institution"
  | "competitor"
  | "expert"
  | "any";

export function roleMatches(userRole: string, required: AppRole | AppRole[]): boolean {
  const need = Array.isArray(required) ? required : [required];
  return need.some((r) => {
    if (r === "any") return true;
    if (r === "admin") return isAdminRole(userRole);
    if (r === "institution") return isInstitutionRole(userRole);
    if (r === "competitor") return isCompetitorRole(userRole);
    if (r === "expert") return isExpertRole(userRole);
    return false;
  });
}

export function homeForRole(role: string, mustChangePassword?: boolean): string {
  if (mustChangePassword) return "/account/change-password";
  if (isAdminRole(role)) return "/admin";
  if (isInstitutionRole(role)) return "/institution";
  if (isCompetitorRole(role)) return "/competitor";
  if (isExpertRole(role)) return "/expert";
  return "/";
}
