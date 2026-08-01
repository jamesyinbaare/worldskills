"use client";

import Link from "next/link";
import {
  FormEvent,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Camera,
  CheckCircle2,
  GraduationCap,
  MapPin,
  ShieldCheck,
  UserRound,
  BookUser,
} from "lucide-react";
import {
  ApiError,
  createRegistration,
  getNominationQuotas,
  getPublicCompetition,
  getRegistrationDraft,
  getRegistrationDraftPhoto,
  getRegistrationForm,
  isCompetitorRole,
  isInstitutionRole,
  listAvailableSkills,
  listMyRegistrations,
  listRegions,
  putRegistrationDraft,
  type AvailableSkillOut,
  type NominationQuotaOut,
  type RegionOut,
  type RegistrationCreateInput,
  type RegistrationDraftInput,
  type RegistrationFormField,
  type RegistrationFormOut,
  type CoachBioInput,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { saveRegistrationConfirmation } from "@/lib/registrationConfirmation";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { RegistrationProgress } from "@/components/registration/RegistrationProgress";
import {
  clampStep,
  type RegistrationStepId,
} from "@/components/registration/registrationSteps";
import {
  SchoolSearchSelect,
  type SchoolSelection,
} from "@/components/registration/SchoolSearchSelect";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const DRAFT_VALUE_KEYS = [
  "givenNames",
  "familyName",
  "gender",
  "dateOfBirth",
  "email",
  "mobile",
  "whatsapp",
  "nationalId",
  "idDocumentKind",
  "otherIdType",
  "nationality",
  "guardianName",
  "guardianEmail",
  "guardianPhone",
  "heardAbout",
  "affiliationType",
  "organizationName",
  "organizationCity",
  "organizationPhone",
  "organizationEmail",
] as const;

function asDateInput(value: unknown): string {
  if (value == null || value === "") return "";
  return String(value).slice(0, 10);
}

function formatDraftSavedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const SPECIAL_FIELDS = new Set([
  "skillIds",
  "photo",
  "declarationAccepted",
  "captchaToken",
  "institutionId",
  "zoneId",
  "regionId",
  "hasPassport",
  "passportNumber",
  "passportExpiresOn",
  "coach",
  "idDocumentKind",
  "otherIdType",
  "nationalId",
  "whatsapp",
  "guardianName",
  "guardianPhone",
  "guardianEmail",
  "heardAbout",
  "affiliationType",
  "organizationName",
  "organizationCity",
  "organizationPhone",
  "organizationEmail",
]);

const INSTITUTION_HIDDEN_FIELDS = new Set([
  "guardianName",
  "guardianEmail",
  "guardianPhone",
]);

const OTHER_ID_TYPES = ["Passport", "Driver's License", "Student ID"] as const;
const HEARD_ABOUT_OPTIONS = [
  "Facebook",
  "Newspaper",
  "Internet",
  "FRIEND",
  "Other",
] as const;

function labelFor(name: string): string {
  const map: Record<string, string> = {
    givenNames: "Given names",
    familyName: "Family name",
    gender: "Gender",
    dateOfBirth: "Date of birth",
    email: "Email",
    mobile: "Mobile / phone",
    whatsapp: "WhatsApp number",
    nationalId: "ID number",
    idDocumentKind: "ID document",
    otherIdType: "Other ID type",
    guardianName: "Guardian name",
    guardianEmail: "Guardian email",
    guardianPhone: "Guardian phone",
    heardAbout: "How did you hear about WSGH?",
    hasPassport: "Passport",
    passportNumber: "Passport number",
    passportExpiresOn: "Passport expiry date",
    affiliationType: "Affiliation",
    organizationName: "Organisation name",
    organizationCity: "City / town",
    organizationPhone: "Organisation phone",
    organizationEmail: "Organisation email",
  };
  return map[name] ?? name;
}

function inputTypeFor(field: RegistrationFormField): string {
  if (field.type === "email") return "email";
  if (field.type === "date") return "date";
  if (field.type === "phone") return "tel";
  return "text";
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Could not read file"));
        return;
      }
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}

function FormSection({
  icon: Icon,
  title,
  description,
  children,
  className,
}: {
  icon: typeof UserRound;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "animate-comp-fade space-y-4 rounded-2xl border border-border/80 bg-white/80 p-5 shadow-[0_1px_0_rgba(0,55,100,0.04)] backdrop-blur-sm sm:p-6",
        className,
      )}
    >
      <header className="flex items-start gap-3">
        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-blue/10 text-brand-blue">
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 space-y-1">
          <h2 className="text-base font-semibold tracking-tight text-primary sm:text-lg">
            {title}
          </h2>
          {description ? (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export type CompetitionRegistrationFormProps = {
  competitionId: string;
  mode: "competitor" | "institution";
  backHref: string;
  confirmationHref: string;
};

export function CompetitionRegistrationForm({
  competitionId,
  mode,
  backHref,
  confirmationHref,
}: CompetitionRegistrationFormProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const preferredSkillId = searchParams.get("skillId");
  const formHintId = useId();
  const { status, me } = useAuth();

  const [competitionName, setCompetitionName] = useState<string | null>(null);
  const [formDef, setFormDef] = useState<RegistrationFormOut | null>(null);
  const [skills, setSkills] = useState<AvailableSkillOut[]>([]);
  const [quotas, setQuotas] = useState<NominationQuotaOut[]>([]);
  const [regions, setRegions] = useState<RegionOut[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [loadingForm, setLoadingForm] = useState(true);

  const [values, setValues] = useState<Record<string, string>>({});
  const [skillIds, setSkillIds] = useState<string[]>([""]);
  const [school, setSchool] = useState<SchoolSelection>(null);
  const [schoolManualMode, setSchoolManualMode] = useState(false);
  const [regionId, setRegionId] = useState("");
  const [hasPassport, setHasPassport] = useState<boolean | null>(null);
  const [passportNumber, setPassportNumber] = useState("");
  const [passportExpiresOn, setPassportExpiresOn] = useState("");
  const [declarationAccepted, setDeclarationAccepted] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("ok");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoClientError, setPhotoClientError] = useState<string | null>(null);
  const [coach, setCoach] = useState({
    surname: "",
    firstName: "",
    otherName: "",
    contactNumber: "",
    email: "",
    whatsapp: "",
    dateOfBirth: "",
  });

  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [checkingExisting, setCheckingExisting] = useState(
    mode === "competitor",
  );
  const [currentStep, setCurrentStep] = useState<RegistrationStepId>(1);
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [draftPending, setDraftPending] = useState(false);
  const [hasSavedPhoto, setHasSavedPhoto] = useState(false);

  const idempotencyKeyRef = useRef(newIdempotencyKey());

  const nextPath =
    preferredSkillId && pathname
      ? `${pathname}?skillId=${encodeURIComponent(preferredSkillId)}`
      : pathname || backHref;
  const loginHref = `/login?next=${encodeURIComponent(nextPath)}`;
  const signupHref =
    mode === "institution"
      ? `/signup/institution?next=${encodeURIComponent(nextPath)}`
      : `/signup?next=${encodeURIComponent(nextPath)}`;

  const sessionInstitutionId =
    me?.institutionId ?? me?.institution_id ?? null;

  useEffect(() => {
    if (status === "loading") return;
    if (status === "anonymous") {
      router.replace(signupHref);
    }
  }, [status, router, signupHref]);

  useEffect(() => {
    if (mode !== "competitor") {
      setCheckingExisting(false);
      return;
    }
    if (status === "loading") return;
    if (status !== "authenticated" || !isCompetitorRole(me?.role ?? "")) {
      setCheckingExisting(false);
      return;
    }

    let cancelled = false;
    setCheckingExisting(true);
    void (async () => {
      let redirected = false;
      try {
        const rows = await listMyRegistrations();
        if (cancelled) return;
        const existing = rows.find((r) => r.competitionId === competitionId);
        if (existing && existing.status?.toUpperCase() !== "DRAFT") {
          redirected = true;
          router.replace(`/competitor/competitions/${competitionId}`);
          return;
        }
      } catch {
        /* Fall through to the registration form */
      } finally {
        if (!cancelled && !redirected) setCheckingExisting(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mode, status, me?.role, competitionId, router]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const pub = await getPublicCompetition(competitionId);
        if (!cancelled) setCompetitionName(pub.name);
      } catch {
        /* title is optional context */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [competitionId]);

  const loadForm = useCallback(async () => {
    if (status !== "authenticated") return;
    if (mode === "competitor" && checkingExisting) return;
    setLoadingForm(true);
    setLoadError(null);
    try {
      const [def, available, regionList] = await Promise.all([
        getRegistrationForm(competitionId),
        listAvailableSkills(competitionId),
        listRegions(),
      ]);
      setFormDef(def);
      const activeSkills = available.filter((s) => s.active);
      setSkills(activeSkills);
      setRegions(regionList.filter((r) => r.active));

      if (mode === "institution") {
        try {
          const q = await getNominationQuotas(competitionId);
          setQuotas(q.quotas);
        } catch {
          setQuotas([]);
        }
      } else {
        setQuotas([]);
      }

      if (def.readOnly) {
        setLoadError(
          new ApiError(403, {
            error: {
              code: "WINDOW_CLOSED",
              message:
                "The registration window is closed for this competition. The form is read-only.",
              fields: [{ name: "window", reason: "WINDOW_CLOSED" }],
              traceId: "",
            },
          }),
        );
      }
      const slotCount = Math.max(1, Math.min(def.maxSkills, 1));
      let preferred =
        preferredSkillId &&
        activeSkills.some((s) => s.skillId === preferredSkillId)
          ? preferredSkillId
          : "";

      if (mode === "competitor") {
        try {
          const draft = await getRegistrationDraft(competitionId);
          const nextValues: Record<string, string> = {};
          for (const key of DRAFT_VALUE_KEYS) {
            const raw = draft[key];
            if (raw == null || raw === "") continue;
            nextValues[key] =
              key === "dateOfBirth" ? asDateInput(raw) : String(raw);
          }
          // Do not restore a lone ID kind without a number — it would force entry.
          if (nextValues.idDocumentKind && !nextValues.nationalId?.trim()) {
            delete nextValues.idDocumentKind;
            delete nextValues.otherIdType;
          }
          setValues(nextValues);

          if (draft.hasPassport != null) setHasPassport(draft.hasPassport);
          setPassportNumber(draft.passportNumber?.trim() ?? "");
          setPassportExpiresOn(asDateInput(draft.passportExpiresOn));

          if (draft.coach && typeof draft.coach === "object") {
            setCoach({
              surname: draft.coach.surname ?? "",
              firstName: draft.coach.firstName ?? "",
              otherName: draft.coach.otherName ?? "",
              contactNumber: draft.coach.contactNumber ?? "",
              email: draft.coach.email ?? "",
              whatsapp: draft.coach.whatsapp ?? "",
              dateOfBirth: asDateInput(draft.coach.dateOfBirth),
            });
          }

          if (draft.institutionId) {
            setSchool({
              institutionId: String(draft.institutionId),
              code: draft.institutionCode?.trim() ?? "",
              name:
                draft.institutionName?.trim() ||
                draft.institutionCode?.trim() ||
                "Selected school",
            });
            setSchoolManualMode(false);
            setRegionId("");
          } else {
            setSchool(null);
            setRegionId(draft.regionId ? String(draft.regionId) : "");
            const aff = String(draft.affiliationType ?? "school");
            setSchoolManualMode(
              aff === "school" && Boolean(draft.organizationName),
            );
          }

          const draftSkills = (draft.skillIds ?? [])
            .map((id) => String(id))
            .filter(Boolean);
          if (draftSkills.length > 0) {
            setSkillIds(
              Array.from(
                { length: Math.max(slotCount, Math.min(draftSkills.length, def.maxSkills)) },
                (_, i) => draftSkills[i] ?? "",
              ),
            );
          } else {
            setSkillIds(
              Array.from({ length: slotCount }, (_, i) =>
                i === 0 && preferred ? preferred : "",
              ),
            );
          }

          if (draft.declarationAccepted != null) {
            setDeclarationAccepted(Boolean(draft.declarationAccepted));
          }
          setCurrentStep(clampStep(draft.currentStep ?? 1));
          setHasSavedPhoto(Boolean(draft.hasPhoto));
          setDraftSavedAt(draft.updatedAt);

          if (draft.hasPhoto) {
            try {
              const blob = await getRegistrationDraftPhoto(competitionId);
              setPhotoPreview((prev) => {
                if (prev) URL.revokeObjectURL(prev);
                return URL.createObjectURL(blob);
              });
            } catch {
              /* Keep hasSavedPhoto fallback UI */
            }
          }
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 404)) {
            /* Soft-fail draft load; form still usable */
          }
          setSkillIds(
            Array.from({ length: slotCount }, (_, i) =>
              i === 0 && preferred ? preferred : "",
            ),
          );
        }
      } else {
        setSkillIds(
          Array.from({ length: slotCount }, (_, i) =>
            i === 0 && preferred ? preferred : "",
          ),
        );
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setLoadError(err);
      } else {
        setLoadError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not load registration form",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setLoadingForm(false);
    }
  }, [competitionId, status, preferredSkillId, mode, checkingExisting]);

  useEffect(() => {
    void loadForm();
  }, [loadForm]);

  useEffect(() => {
    return () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview);
    };
  }, [photoPreview]);

  function setValue(name: string, value: string) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function updateSkillAt(index: number, value: string) {
    setSkillIds((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  }

  function addSkillSlot() {
    if (!formDef) return;
    setSkillIds((prev) => {
      if (prev.length >= formDef.maxSkills) return prev;
      return [...prev, ""];
    });
  }

  function removeSkillSlot(index: number) {
    setSkillIds((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== index);
    });
  }

  function onSchoolChange(next: SchoolSelection) {
    setSchool(next);
    if (next) {
      setRegionId("");
      setSchoolManualMode(false);
      setValue("organizationName", "");
      setValue("affiliationType", "school");
    }
    setFieldErrors((prev) => {
      const copy = { ...prev };
      delete copy.institutionId;
      delete copy.schoolCode;
      delete copy.code;
      delete copy.regionId;
      delete copy.organizationName;
      return copy;
    });
  }

  function affiliationType(): string {
    if (mode === "institution") return "school";
    return values.affiliationType?.trim() || "school";
  }

  async function onPhotoChange(file: File | null) {
    setPhotoClientError(null);
    setPhotoFile(null);
    if (photoPreview) {
      URL.revokeObjectURL(photoPreview);
      setPhotoPreview(null);
    }
    if (!file || !formDef) return;

    const maxBytes = formDef.photoMaxMb * 1024 * 1024;
    if (file.size > maxBytes) {
      setPhotoClientError(
        `Photo must be ${formDef.photoMaxMb} MB or smaller (${formDef.photoFormats.join(", ") || "image"}).`,
      );
      return;
    }
    if (
      formDef.photoFormats.length > 0 &&
      !formDef.photoFormats.includes(file.type)
    ) {
      setPhotoClientError(
        `Photo must be one of: ${formDef.photoFormats.join(", ")}.`,
      );
      return;
    }
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
  }

  async function buildDraftPayload(
    step?: number,
  ): Promise<RegistrationDraftInput> {
    const payload: RegistrationDraftInput = {
      currentStep: step ?? currentStep,
      skillIds: skillIds.map((s) => s.trim()).filter(Boolean),
      declarationAccepted,
      hasPassport,
      passportNumber:
        hasPassport === true ? passportNumber.trim() || null : null,
      passportExpiresOn:
        hasPassport === true ? passportExpiresOn.trim() || null : null,
      captchaToken: captchaToken.trim() || null,
    };

    for (const key of DRAFT_VALUE_KEYS) {
      const raw = values[key]?.trim() ?? "";
      if (raw) {
        (payload as Record<string, unknown>)[key] = raw;
      }
    }

    const aff = affiliationType();
    payload.affiliationType = aff;
    if (aff === "school" && school?.institutionId && mode !== "institution") {
      payload.organizationName = null;
      payload.organizationCity = null;
    }

    const coachPayload: CoachBioInput = {
      surname: coach.surname.trim(),
      firstName: coach.firstName.trim(),
      otherName: coach.otherName.trim() || null,
      contactNumber: coach.contactNumber.trim(),
      email: coach.email.trim(),
      whatsapp: coach.whatsapp.trim(),
      dateOfBirth: coach.dateOfBirth.trim(),
    };
    if (
      coachPayload.surname ||
      coachPayload.firstName ||
      coachPayload.contactNumber ||
      coachPayload.email ||
      coachPayload.whatsapp ||
      coachPayload.dateOfBirth
    ) {
      payload.coach = coachPayload;
    }

    if (mode === "institution") {
      payload.institutionId = sessionInstitutionId;
      payload.affiliationType = "school";
      payload.organizationName = null;
      payload.organizationCity = null;
    } else if (aff === "school" && school?.institutionId) {
      payload.institutionId = school.institutionId;
      payload.regionId = null;
      payload.organizationName = null;
      payload.organizationCity = null;
    } else {
      payload.institutionId = null;
      payload.regionId = regionId || null;
    }

    if (photoFile) {
      payload.photo = {
        contentBase64: await readFileAsBase64(photoFile),
        contentType: photoFile.type || "image/png",
      };
    }

    return payload;
  }

  async function saveDraft(step?: number): Promise<boolean> {
    if (mode !== "competitor" || status !== "authenticated") return true;
    setDraftPending(true);
    try {
      const payload = await buildDraftPayload(step);
      const out = await putRegistrationDraft(competitionId, payload);
      setDraftSavedAt(out.updatedAt);
      if (photoFile || out.hasPhoto) {
        setHasSavedPhoto(Boolean(out.hasPhoto) || Boolean(photoFile));
      }
      setError(null);
      return true;
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not save draft",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
      return false;
    } finally {
      setDraftPending(false);
    }
  }

  function validateStep(step: number): boolean {
    if (!formDef) return false;
    setError(null);
    const nextErrors: Record<string, string> = {};
    const stepStandardFields = formDef.fields.filter(
      (f) =>
        !SPECIAL_FIELDS.has(f.name) &&
        !(mode === "institution" && INSTITUTION_HIDDEN_FIELDS.has(f.name)),
    );
    const stepHasDeclaration = formDef.fields.some(
      (f) => f.name === "declarationAccepted",
    );

    if (step === 1) {
      for (const field of stepStandardFields) {
        if (!field.required) continue;
        const raw = values[field.name]?.trim() ?? "";
        if (!raw) {
          nextErrors[field.name] =
            field.name === "dateOfBirth"
              ? "Enter your date of birth."
              : "This field is required.";
        }
      }
      const idKind = values.idDocumentKind?.trim() || "";
      if (idKind === "OTHER" && !values.otherIdType?.trim()) {
        nextErrors.otherIdType = "Select the type of ID.";
      }
      if (idKind && !values.nationalId?.trim()) {
        nextErrors.nationalId = "Enter your ID number.";
      }
      if (!idKind && values.nationalId?.trim()) {
        nextErrors.idDocumentKind = "Select Ghana Card or Other ID.";
      }
      if (!values.heardAbout?.trim()) {
        nextErrors.heardAbout = "Tell us how you heard about WSGH.";
      }
      if (!values.whatsapp?.trim()) {
        nextErrors.whatsapp = "Enter your WhatsApp number.";
      }
      const photoRequired = formDef.fields.some(
        (f) => f.name === "photo" && f.required,
      );
      if (photoClientError) {
        nextErrors.photo = photoClientError;
      } else if (photoRequired && !photoFile && !hasSavedPhoto) {
        nextErrors.photo = "Please upload your photo.";
      }
    }

    if (step === 2) {
      if (hasPassport === null) {
        nextErrors.hasPassport = "Tell us whether you have a passport.";
      } else if (hasPassport) {
        if (!passportNumber.trim()) {
          nextErrors.passportNumber = "Enter your passport number.";
        }
        if (!passportExpiresOn.trim()) {
          nextErrors.passportExpiresOn = "Enter your passport expiry date.";
        }
      }
    }

    if (step === 3) {
      const trimmedSkills = skillIds.map((s) => s.trim()).filter(Boolean);
      if (trimmedSkills.length !== formDef.maxSkills) {
        nextErrors.skillIds = `Select exactly ${formDef.maxSkills} skill(s)`;
      }
      const aff = affiliationType();
      if (mode === "competitor" && !aff) {
        nextErrors.affiliationType = "Select school, company, or workshop.";
      }
      if (!values.organizationPhone?.trim()) {
        nextErrors.organizationPhone = "Enter the organisation phone number.";
      }
      if (!values.organizationEmail?.trim()) {
        nextErrors.organizationEmail = "Enter the organisation email address.";
      }
      if (mode === "competitor") {
        if (aff === "school") {
          if (!school?.institutionId && !schoolManualMode) {
            nextErrors.institutionId =
              "Search for your school, or choose “School not listed”.";
          }
          if (schoolManualMode) {
            if (!values.organizationName?.trim()) {
              nextErrors.organizationName = "Enter the name of your school.";
            }
            if (!regionId) {
              nextErrors.regionId = "Select your region.";
            }
          }
        } else {
          if (!values.organizationName?.trim()) {
            nextErrors.organizationName = `Enter the name of your ${aff}.`;
          }
          if (!regionId) {
            nextErrors.regionId = "Select the location region.";
          }
          if (!values.organizationCity?.trim()) {
            nextErrors.organizationCity = "Enter the city or town.";
          }
        }
      } else {
        // Institution mode still needs org contacts.
        if (!values.organizationPhone?.trim()) {
          nextErrors.organizationPhone = "Enter the organisation phone number.";
        }
      }
    }

    if (step === 4) {
      const coachRequired: Array<{ key: keyof typeof coach; field: string }> = [
        { key: "surname", field: "coach.surname" },
        { key: "firstName", field: "coach.firstName" },
        { key: "contactNumber", field: "coach.contactNumber" },
        { key: "email", field: "coach.email" },
        { key: "whatsapp", field: "coach.whatsapp" },
        { key: "dateOfBirth", field: "coach.dateOfBirth" },
      ];
      for (const { key, field } of coachRequired) {
        if (!coach[key].trim()) {
          nextErrors[field] = "Required";
        }
      }
    }

    if (step === 5) {
      if (stepHasDeclaration && !declarationAccepted) {
        nextErrors.declarationAccepted =
          "Please accept the declaration to continue.";
      }
      if (!captchaToken.trim()) {
        nextErrors.captchaToken = "Complete the security check.";
      }
    }

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError(
        new ApiError(422, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Please fix the highlighted fields before continuing.",
            fields: Object.keys(nextErrors).map((name) => ({
              name,
              reason: "REQUIRED",
            })),
            traceId: "",
          },
        }),
      );
      return false;
    }
    return true;
  }

  async function handleContinue() {
    if (!formDef || formDef.readOnly) return;
    if (!validateStep(currentStep)) return;
    const next = clampStep(currentStep + 1);
    const ok = await saveDraft(next);
    if (!ok) return;
    setCurrentStep(next);
  }

  async function handleSaveDraftClick() {
    setError(null);
    await saveDraft(currentStep);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!formDef || formDef.readOnly) return;

    if (currentStep < 5) {
      await handleContinue();
      return;
    }

    if (!validateStep(5)) return;

    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      if (photoClientError) {
        throw new ApiError(422, {
          error: {
            code: "PHOTO_INVALID",
            message: photoClientError,
            fields: [{ name: "photo", reason: "PHOTO_INVALID" }],
            traceId: "",
          },
        });
      }

      const trimmedSkills = skillIds.map((s) => s.trim()).filter(Boolean);
      if (trimmedSkills.length !== formDef.maxSkills) {
        throw new ApiError(422, {
          error: {
            code: "SKILL_SELECTION_INVALID",
            message: `Select exactly ${formDef.maxSkills} skill(s)`,
            fields: [{ name: "skillIds", reason: "SKILL_SELECTION_INVALID" }],
            traceId: "",
          },
        });
      }

      const payload: RegistrationCreateInput = {
        skillIds: trimmedSkills,
        declarationAccepted,
        captchaToken: captchaToken.trim() || null,
        hasPassport,
        passportNumber:
          hasPassport === true ? passportNumber.trim() || null : null,
        passportExpiresOn:
          hasPassport === true ? passportExpiresOn.trim() || null : null,
      };

      for (const field of formDef.fields) {
        if (SPECIAL_FIELDS.has(field.name)) continue;
        const raw = values[field.name]?.trim() ?? "";
        if (!raw) {
          // Omit empty values — sending "" breaks date/UUID parsing on the API.
          continue;
        }
        (payload as Record<string, unknown>)[field.name] = raw;
      }

      // Special / affiliation / ID fields stored in values
      for (const key of [
        "whatsapp",
        "nationalId",
        "idDocumentKind",
        "otherIdType",
        "guardianName",
        "guardianEmail",
        "guardianPhone",
        "heardAbout",
        "affiliationType",
        "organizationName",
        "organizationCity",
        "organizationPhone",
        "organizationEmail",
      ] as const) {
        const raw = values[key]?.trim() ?? "";
        if (raw) {
          (payload as Record<string, unknown>)[key] = raw;
        }
      }

      const aff = affiliationType();
      payload.affiliationType = aff;
      if (values.idDocumentKind !== "OTHER") {
        payload.otherIdType = null;
      }

      // Client-side required checks with human messages (before API round-trip)
      for (const field of formDef.fields) {
        if (SPECIAL_FIELDS.has(field.name) || !field.required) continue;
        if (mode === "institution" && INSTITUTION_HIDDEN_FIELDS.has(field.name)) {
          continue;
        }
        const raw = values[field.name]?.trim() ?? "";
        if (!raw) {
          throw new ApiError(422, {
            error: {
              code: "VALIDATION_ERROR",
              message:
                field.name === "dateOfBirth"
                  ? "Enter your date of birth."
                  : "Please fill in all required fields.",
              fields: [
                {
                  name: field.name,
                  reason:
                    field.name === "dateOfBirth" ? "INVALID_DATE" : "REQUIRED",
                },
              ],
              traceId: "",
            },
          });
        }
      }

      if (hasPassport === null) {
        throw new ApiError(422, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Tell us whether you have a passport.",
            fields: [{ name: "hasPassport", reason: "REQUIRED" }],
            traceId: "",
          },
        });
      }
      if (hasPassport && !passportNumber.trim()) {
        throw new ApiError(422, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Enter your passport number.",
            fields: [{ name: "passportNumber", reason: "REQUIRED" }],
            traceId: "",
          },
        });
      }
      if (hasPassport && !passportExpiresOn.trim()) {
        throw new ApiError(422, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Enter your passport expiry date.",
            fields: [{ name: "passportExpiresOn", reason: "REQUIRED" }],
            traceId: "",
          },
        });
      }

      const coachRequired: Array<{ key: keyof typeof coach; field: string }> = [
        { key: "surname", field: "coach.surname" },
        { key: "firstName", field: "coach.firstName" },
        { key: "contactNumber", field: "coach.contactNumber" },
        { key: "email", field: "coach.email" },
        { key: "whatsapp", field: "coach.whatsapp" },
        { key: "dateOfBirth", field: "coach.dateOfBirth" },
      ];
      for (const { key, field } of coachRequired) {
        if (!coach[key].trim()) {
          throw new ApiError(422, {
            error: {
              code: "VALIDATION_ERROR",
              message: "Please complete the coach / team leader details.",
              fields: [{ name: field, reason: "REQUIRED" }],
              traceId: "",
            },
          });
        }
      }

      const coachPayload: CoachBioInput = {
        surname: coach.surname.trim(),
        firstName: coach.firstName.trim(),
        otherName: coach.otherName.trim() || null,
        contactNumber: coach.contactNumber.trim(),
        email: coach.email.trim(),
        whatsapp: coach.whatsapp.trim(),
        dateOfBirth: coach.dateOfBirth.trim(),
      };
      payload.coach = coachPayload;

      if (mode === "institution") {
        payload.institutionId = sessionInstitutionId;
        payload.affiliationType = "school";
        payload.organizationName = null;
        payload.organizationCity = null;
      } else if (aff === "school" && school?.institutionId) {
        payload.institutionId = school.institutionId;
        payload.regionId = null;
        payload.organizationName = null;
        payload.organizationCity = null;
      } else {
        payload.institutionId = null;
        if (regionId) {
          payload.regionId = regionId;
        }
      }

      const photoRequired = formDef.fields.some(
        (f) => f.name === "photo" && f.required,
      );
      if (photoFile) {
        const contentBase64 = await readFileAsBase64(photoFile);
        payload.photo = {
          contentBase64,
          contentType: photoFile.type || "image/png",
        };
      } else if (photoRequired && !hasSavedPhoto) {
        payload.photo = null;
      }

      const out = await createRegistration(
        competitionId,
        payload,
        idempotencyKeyRef.current,
      );
      saveRegistrationConfirmation(competitionId, out);
      idempotencyKeyRef.current = newIdempotencyKey();
      router.push(confirmationHref);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not submit registration",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setPending(false);
    }
  }

  const readOnly = Boolean(formDef?.readOnly);
  const standardFields =
    formDef?.fields.filter(
      (f) =>
        !SPECIAL_FIELDS.has(f.name) &&
        !(mode === "institution" && INSTITUTION_HIDDEN_FIELDS.has(f.name)),
    ) ?? [];
  const hasDeclaration = formDef?.fields.some(
    (f) => f.name === "declarationAccepted",
  );
  const hasPhoto = formDef?.fields.some((f) => f.name === "photo");
  const hasSkills = formDef?.fields.some((f) => f.name === "skillIds");
  const quotaBySkill = Object.fromEntries(
    quotas.map((q) => [q.skillId, q]),
  ) as Record<string, NominationQuotaOut>;
  const summaryName =
    [values.givenNames, values.familyName].filter(Boolean).join(" ") || "—";
  const summarySkill =
    skillIds
      .map((id) => skills.find((s) => s.skillId === id)?.name)
      .filter(Boolean)
      .join(", ") || "—";
  const summarySchool =
    mode === "institution"
      ? "Your claimed school"
      : (() => {
          const aff = affiliationType();
          if (aff === "school" && school?.name) {
            return school.code
              ? `${school.name} (${school.code})`
              : school.name;
          }
          const orgName = values.organizationName?.trim();
          const regionName = regionId
            ? (regions.find((r) => r.regionId === regionId)?.name ?? null)
            : null;
          const city = values.organizationCity?.trim();
          if (orgName) {
            const bits = [
              `${aff.charAt(0).toUpperCase()}${aff.slice(1)}: ${orgName}`,
              city,
              regionName,
            ].filter(Boolean);
            return bits.join(" · ");
          }
          return regionName ?? "—";
        })();
  const summaryId = !values.idDocumentKind && !values.nationalId
    ? "—"
    : values.idDocumentKind === "OTHER"
      ? `${values.otherIdType || "Other ID"} · ${values.nationalId || "—"}`
      : values.idDocumentKind === "GHANA_CARD"
        ? `Ghana Card · ${values.nationalId || "—"}`
        : values.nationalId || "—";
  const authLoading = status === "loading" || status === "anonymous";
  const wrongRole =
    status === "authenticated" &&
    me &&
    ((mode === "competitor" && !isCompetitorRole(me.role)) ||
      (mode === "institution" && !isInstitutionRole(me.role)));

  if (authLoading) {
    return (
      <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
        <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-14">
          <Alert data-testid="registration-auth-required">
            <AlertTitle>Account required</AlertTitle>
            <AlertDescription>
              Please{" "}
              <Link
                href={loginHref}
                className="font-medium underline underline-offset-2"
              >
                sign in
              </Link>{" "}
              or{" "}
              <Link
                href={signupHref}
                className="font-medium underline underline-offset-2"
              >
                create an account
              </Link>{" "}
              to continue.
            </AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  if (checkingExisting) {
    return (
      <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
        <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-14">
          <p
            className="text-sm text-muted-foreground"
            role="status"
            data-testid="registration-checking-existing"
          >
            Checking your registration…
          </p>
        </div>
      </div>
    );
  }

  if (wrongRole) {
    return (
      <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
        <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-14">
          <Alert data-testid="registration-wrong-role">
            <AlertTitle>
              {mode === "competitor"
                ? "Competitor account required"
                : "Institution account required"}
            </AlertTitle>
            <AlertDescription>
              This registration page is not available for your current role.
            </AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
      <div className="mx-auto max-w-2xl space-y-8 px-4 py-8 sm:px-6 sm:py-12">
        <div className="animate-comp-fade space-y-4">
          <Button variant="link" className="h-auto min-h-11 px-0" asChild>
            <Link href={backHref}>← Back</Link>
          </Button>

          <header className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-blue/70">
              WorldSkills Ghana
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-primary sm:text-4xl">
              {mode === "institution"
                ? "Register a competitor"
                : "Competition registration"}
            </h1>
            {competitionName ? (
              <p className="text-lg font-medium text-foreground/90">
                {competitionName}
              </p>
            ) : null}
            <p
              id={formHintId}
              className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base"
            >
              {mode === "institution"
                ? "Students are registered under your school. No competitor account is required."
                : `Signed in as ${me?.email ?? me?.full_name}. Search for your school, or choose a region if you are unaffiliated.`}
            </p>
          </header>

          {formDef ? (
            <div className="space-y-2">
              <RegistrationProgress
                currentStep={currentStep}
                onStepSelect={(s) => setCurrentStep(s)}
              />
              {draftSavedAt ? (
                <p
                  className="text-xs text-muted-foreground"
                  data-testid="registration-draft-saved-at"
                >
                  Last saved {formatDraftSavedAt(draftSavedAt)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        {loadingForm ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading form…
          </p>
        ) : null}

        {loadError ? (
          <div data-testid="registration-window-alert">
            <ApiErrorAlert
              error={loadError}
              title={
                loadError.code === "WINDOW_CLOSED"
                  ? "Registration closed"
                  : "Could not load form"
              }
            />
          </div>
        ) : null}

        {formDef ? (
          <form
            onSubmit={onSubmit}
            className="space-y-5 pb-24"
            noValidate
            data-testid="registration-form"
            aria-describedby={formHintId}
          >
            {currentStep === 1 && (
              <>
            <FormSection
              icon={UserRound}
              title="Your details"
              description="Use the same details as on your national ID where possible."
            >
              <div className="grid gap-4 sm:grid-cols-2">
                {(() => {
                  let injectedWhatsapp = false;
                  const nodes = standardFields.map((field) => {
                    const err = fieldErrors[field.name];
                    const errId = `${field.name}-error`;
                    const wide =
                      field.name === "email" ||
                      field.name === "nationalId" ||
                      field.name === "guardianEmail";
                    const enumValues =
                      field.type === "enum" || field.name === "gender"
                        ? field.allowedValues?.length
                          ? field.allowedValues
                          : ["Male", "Female"]
                        : null;
                    const fieldNode = (
                      <div
                        key={field.name}
                        className={cn("space-y-2", wide && "sm:col-span-2")}
                      >
                        <Label htmlFor={field.name}>
                          {labelFor(field.name)}
                          {field.required ? " *" : ""}
                        </Label>
                        {enumValues ? (
                          <select
                            id={field.name}
                            name={field.name}
                            className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            required={field.required}
                            value={values[field.name] ?? ""}
                            disabled={readOnly || pending || draftPending}
                            aria-invalid={Boolean(err)}
                            aria-describedby={err ? errId : undefined}
                            onChange={(e) => setValue(field.name, e.target.value)}
                            data-testid={`registration-field-${field.name}`}
                          >
                            <option value="">
                              Select {labelFor(field.name).toLowerCase()}
                            </option>
                            {enumValues.map((opt) => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Input
                            id={field.name}
                            name={field.name}
                            type={inputTypeFor(field)}
                            className="min-h-11"
                            required={field.required}
                            maxLength={field.maxLength ?? undefined}
                            pattern={field.pattern ?? undefined}
                            value={values[field.name] ?? ""}
                            disabled={readOnly || pending || draftPending}
                            aria-invalid={Boolean(err)}
                            aria-describedby={err ? errId : undefined}
                            onChange={(e) => setValue(field.name, e.target.value)}
                            autoComplete="off"
                          />
                        )}
                        <FieldMessage id={errId} message={err} />
                      </div>
                    );
                    if (field.name !== "mobile") {
                      return fieldNode;
                    }
                    injectedWhatsapp = true;
                    return (
                      <div key="mobile-whatsapp" className="contents">
                        {fieldNode}
                        <div className="space-y-2">
                          <Label htmlFor="whatsapp">WhatsApp number *</Label>
                          <Input
                            id="whatsapp"
                            name="whatsapp"
                            type="tel"
                            className="min-h-11"
                            value={values.whatsapp ?? ""}
                            disabled={readOnly || pending || draftPending}
                            aria-invalid={Boolean(fieldErrors.whatsapp)}
                            onChange={(e) => setValue("whatsapp", e.target.value)}
                            autoComplete="off"
                            data-testid="registration-field-whatsapp"
                          />
                          <FieldMessage message={fieldErrors.whatsapp} />
                        </div>
                      </div>
                    );
                  });
                  if (!injectedWhatsapp) {
                    nodes.push(
                      <div key="whatsapp" className="space-y-2">
                        <Label htmlFor="whatsapp">WhatsApp number *</Label>
                        <Input
                          id="whatsapp"
                          name="whatsapp"
                          type="tel"
                          className="min-h-11"
                          value={values.whatsapp ?? ""}
                          disabled={readOnly || pending || draftPending}
                          aria-invalid={Boolean(fieldErrors.whatsapp)}
                          onChange={(e) => setValue("whatsapp", e.target.value)}
                          autoComplete="off"
                          data-testid="registration-field-whatsapp"
                        />
                        <FieldMessage message={fieldErrors.whatsapp} />
                      </div>,
                    );
                  }
                  return nodes;
                })()}
              </div>
            </FormSection>

            {mode === "competitor" ? (
              <FormSection
                icon={UserRound}
                title="Guardian"
                description="Parent or guardian contact details."
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="guardianName">Guardian name</Label>
                    <Input
                      id="guardianName"
                      name="guardianName"
                      className="min-h-11"
                      value={values.guardianName ?? ""}
                      disabled={readOnly || pending || draftPending}
                      aria-invalid={Boolean(fieldErrors.guardianName)}
                      onChange={(e) => setValue("guardianName", e.target.value)}
                      autoComplete="off"
                      data-testid="registration-field-guardianName"
                    />
                    <FieldMessage message={fieldErrors.guardianName} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="guardianPhone">Guardian phone</Label>
                    <Input
                      id="guardianPhone"
                      name="guardianPhone"
                      type="tel"
                      className="min-h-11"
                      value={values.guardianPhone ?? ""}
                      disabled={readOnly || pending || draftPending}
                      aria-invalid={Boolean(fieldErrors.guardianPhone)}
                      onChange={(e) => setValue("guardianPhone", e.target.value)}
                      autoComplete="off"
                      data-testid="registration-field-guardianPhone"
                    />
                    <FieldMessage message={fieldErrors.guardianPhone} />
                  </div>
                </div>
              </FormSection>
            ) : null}

            <FormSection
              icon={BookUser}
              title="Identification"
              description="Optionally enter your Ghana Card number, or choose another accepted ID."
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2 sm:col-span-2">
                  <Label>ID document (optional)</Label>
                  <div className="flex flex-wrap gap-3">
                    {(
                      [
                        { value: "GHANA_CARD", label: "Ghana Card" },
                        { value: "OTHER", label: "Other ID" },
                      ] as const
                    ).map((opt) => {
                      const selected = values.idDocumentKind === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          className={cn(
                            "flex min-h-11 items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
                            selected
                              ? "border-brand-blue bg-brand-blue/10 text-foreground"
                              : "border-input bg-background hover:bg-muted/50",
                          )}
                          disabled={readOnly || pending || draftPending}
                          aria-pressed={selected}
                          data-testid={`id-kind-${opt.value}`}
                          onClick={() => {
                            if (selected) {
                              setValue("idDocumentKind", "");
                              setValue("otherIdType", "");
                              return;
                            }
                            setValue("idDocumentKind", opt.value);
                            if (opt.value !== "OTHER") {
                              setValue("otherIdType", "");
                            }
                          }}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                  <FieldMessage message={fieldErrors.idDocumentKind} />
                </div>

                {values.idDocumentKind === "OTHER" ? (
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor="otherIdType">Other ID type *</Label>
                    <select
                      id="otherIdType"
                      className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={values.otherIdType ?? ""}
                      disabled={readOnly || pending || draftPending}
                      onChange={(e) => setValue("otherIdType", e.target.value)}
                      data-testid="other-id-type"
                    >
                      <option value="">Select ID type</option>
                      {OTHER_ID_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <FieldMessage message={fieldErrors.otherIdType} />
                  </div>
                ) : null}

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="nationalId">
                    {values.idDocumentKind === "OTHER"
                      ? "ID number *"
                      : values.idDocumentKind === "GHANA_CARD"
                        ? "Ghana Card number *"
                        : "ID number (optional)"}
                  </Label>
                  <Input
                    id="nationalId"
                    name="nationalId"
                    className="min-h-11 font-mono"
                    value={values.nationalId ?? ""}
                    disabled={readOnly || pending || draftPending}
                    aria-invalid={Boolean(fieldErrors.nationalId)}
                    onChange={(e) => setValue("nationalId", e.target.value)}
                    autoComplete="off"
                    data-testid="registration-field-nationalId"
                  />
                  <FieldMessage message={fieldErrors.nationalId} />
                </div>
              </div>
            </FormSection>

            {hasPhoto ? (
              <FormSection
                icon={Camera}
                title="Photo"
                description={`Accepted: ${formDef.photoFormats.join(", ") || "image files"}; max ${formDef.photoMaxMb} MB.`}
              >
                <div className="space-y-3">
                  <Label htmlFor="photo" className="sr-only">
                    Photo *
                  </Label>
                  <label
                    htmlFor="photo"
                    className={cn(
                      "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-brand-blue/30 bg-brand-blue/[0.03] px-4 py-8 text-center transition-colors hover:bg-brand-blue/[0.06]",
                      (readOnly || pending || draftPending) && "pointer-events-none opacity-60",
                    )}
                  >
                    {photoPreview ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={photoPreview}
                        alt="Selected registration photo preview"
                        className="size-28 rounded-lg object-cover ring-2 ring-brand-gold/50"
                      />
                    ) : hasSavedPhoto ? (
                      <div className="space-y-1">
                        <Camera
                          className="mx-auto size-8 text-brand-blue/70"
                          aria-hidden
                        />
                        <p className="text-sm font-medium text-foreground">
                          Photo already saved
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Upload a new file to replace it
                        </p>
                      </div>
                    ) : (
                      <Camera
                        className="size-8 text-brand-blue/70"
                        aria-hidden
                      />
                    )}
                    <span className="text-sm font-medium text-foreground">
                      {photoFile
                        ? photoFile.name
                        : hasSavedPhoto
                          ? "Replace photo"
                          : "Click to upload your photo"}
                    </span>
                  </label>
                  <Input
                    id="photo"
                    type="file"
                    accept={formDef.photoFormats.join(",") || "image/*"}
                    className="sr-only"
                    disabled={readOnly || pending || draftPending}
                    aria-describedby={
                      photoClientError || fieldErrors.photo
                        ? "photo-error"
                        : undefined
                    }
                    aria-invalid={Boolean(
                      photoClientError || fieldErrors.photo,
                    )}
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null;
                      void onPhotoChange(file);
                    }}
                    data-testid="registration-photo"
                  />
                  <FieldMessage
                    id="photo-error"
                    message={photoClientError || fieldErrors.photo}
                  />
                </div>
              </FormSection>
            ) : null}

            <FormSection
              icon={UserRound}
              title="How did you hear about WSGH?"
              description="Tell us how you found WorldSkills Ghana."
            >
              <div className="space-y-2">
                <Label htmlFor="heardAbout">Source *</Label>
                <select
                  id="heardAbout"
                  name="heardAbout"
                  className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={values.heardAbout ?? ""}
                  disabled={readOnly || pending || draftPending}
                  aria-invalid={Boolean(fieldErrors.heardAbout)}
                  onChange={(e) => setValue("heardAbout", e.target.value)}
                  data-testid="registration-field-heardAbout"
                >
                  <option value="">Select an option</option>
                  {HEARD_ABOUT_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
                <FieldMessage message={fieldErrors.heardAbout} />
              </div>
            </FormSection>
              </>
            )}

            {currentStep === 2 && (
            <FormSection
              icon={BookUser}
              title="Passport"
              description="Tell us if you hold a valid passport. If yes, enter the passport number and expiry date exactly as printed."
            >
              <fieldset
                className="space-y-3"
                disabled={readOnly || pending || draftPending}
                data-testid="registration-passport"
              >
                <legend className="text-sm font-medium">
                  Do you have a passport? *
                </legend>
                <div className="flex flex-wrap gap-3">
                  <label
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
                      hasPassport === true
                        ? "border-brand-blue bg-brand-blue/10 text-foreground"
                        : "border-input bg-background hover:bg-muted/50",
                    )}
                  >
                    <input
                      type="radio"
                      name="hasPassport"
                      className="size-4 accent-brand-blue"
                      checked={hasPassport === true}
                      onChange={() => {
                        setHasPassport(true);
                        setFieldErrors((prev) => {
                          const next = { ...prev };
                          delete next.hasPassport;
                          return next;
                        });
                      }}
                      data-testid="passport-yes"
                    />
                    Yes
                  </label>
                  <label
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
                      hasPassport === false
                        ? "border-brand-blue bg-brand-blue/10 text-foreground"
                        : "border-input bg-background hover:bg-muted/50",
                    )}
                  >
                    <input
                      type="radio"
                      name="hasPassport"
                      className="size-4 accent-brand-blue"
                      checked={hasPassport === false}
                      onChange={() => {
                        setHasPassport(false);
                        setPassportNumber("");
                        setPassportExpiresOn("");
                        setFieldErrors((prev) => {
                          const next = { ...prev };
                          delete next.hasPassport;
                          delete next.passportNumber;
                          delete next.passportExpiresOn;
                          return next;
                        });
                      }}
                      data-testid="passport-no"
                    />
                    No
                  </label>
                </div>
                <FieldMessage message={fieldErrors.hasPassport} />

                {hasPassport === true ? (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2 sm:col-span-2">
                      <Label htmlFor="passportNumber">Passport number *</Label>
                      <Input
                        id="passportNumber"
                        name="passportNumber"
                        className="min-h-11 font-mono uppercase"
                        value={passportNumber}
                        disabled={readOnly || pending || draftPending}
                        autoComplete="off"
                        placeholder="e.g. G1234567"
                        aria-invalid={Boolean(fieldErrors.passportNumber)}
                        data-testid="passport-number"
                        onChange={(e) => {
                          setPassportNumber(e.target.value.toUpperCase());
                          setFieldErrors((prev) => {
                            const next = { ...prev };
                            delete next.passportNumber;
                            return next;
                          });
                        }}
                      />
                      <FieldMessage message={fieldErrors.passportNumber} />
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                      <Label htmlFor="passportExpiresOn">
                        Passport expiry / valid until *
                      </Label>
                      <Input
                        id="passportExpiresOn"
                        name="passportExpiresOn"
                        type="date"
                        className="min-h-11"
                        value={passportExpiresOn}
                        disabled={readOnly || pending || draftPending}
                        aria-invalid={Boolean(fieldErrors.passportExpiresOn)}
                        data-testid="passport-expires-on"
                        onChange={(e) => {
                          setPassportExpiresOn(e.target.value);
                          setFieldErrors((prev) => {
                            const next = { ...prev };
                            delete next.passportExpiresOn;
                            return next;
                          });
                        }}
                      />
                      <p className="text-xs text-muted-foreground">
                        Use the expiry date printed in your passport.
                      </p>
                      <FieldMessage message={fieldErrors.passportExpiresOn} />
                    </div>
                  </div>
                ) : null}
              </fieldset>
            </FormSection>
            )}

            {currentStep === 3 && (
              <>
            {mode === "institution" ? (
              <FormSection
                icon={MapPin}
                title="School"
                description="Registrations are linked to your claimed school account."
              >
                <p className="rounded-lg border border-dashed border-border bg-muted/40 px-4 py-3 text-sm">
                  Linked to your claimed school account
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="organizationPhone">Organisation phone *</Label>
                    <Input
                      id="organizationPhone"
                      type="tel"
                      className="min-h-11"
                      value={values.organizationPhone ?? ""}
                      disabled={readOnly || pending || draftPending}
                      onChange={(e) =>
                        setValue("organizationPhone", e.target.value)
                      }
                      data-testid="organization-phone"
                    />
                    <FieldMessage message={fieldErrors.organizationPhone} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="organizationEmail">Organisation email *</Label>
                    <Input
                      id="organizationEmail"
                      type="email"
                      className="min-h-11"
                      value={values.organizationEmail ?? ""}
                      disabled={readOnly || pending || draftPending}
                      onChange={(e) =>
                        setValue("organizationEmail", e.target.value)
                      }
                      data-testid="organization-email"
                    />
                    <FieldMessage message={fieldErrors.organizationEmail} />
                  </div>
                </div>
              </FormSection>
            ) : (
              <FormSection
                icon={MapPin}
                title="Affiliation"
                description="Link your registration to a school, company, or workshop."
              >
                <div className="space-y-2">
                  <Label>Affiliation type *</Label>
                  <div className="flex flex-wrap gap-3">
                    {(
                      [
                        { value: "school", label: "School" },
                        { value: "company", label: "Company" },
                        { value: "workshop", label: "Workshop" },
                      ] as const
                    ).map((opt) => (
                      <label
                        key={opt.value}
                        className={cn(
                          "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
                          affiliationType() === opt.value
                            ? "border-brand-blue bg-brand-blue/10 text-foreground"
                            : "border-input bg-background hover:bg-muted/50",
                        )}
                      >
                        <input
                          type="radio"
                          name="affiliationType"
                          className="size-4 accent-brand-blue"
                          checked={affiliationType() === opt.value}
                          disabled={readOnly || pending || draftPending}
                          onChange={() => {
                            setValue("affiliationType", opt.value);
                            setSchool(null);
                            setSchoolManualMode(false);
                            setRegionId("");
                            setValue("organizationName", "");
                            setValue("organizationCity", "");
                          }}
                          data-testid={`affiliation-${opt.value}`}
                        />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                  <FieldMessage message={fieldErrors.affiliationType} />
                </div>

                {affiliationType() === "school" ? (
                  <div className="space-y-4">
                    {!schoolManualMode ? (
                      <div className="space-y-2">
                        <Label>School</Label>
                        <SchoolSearchSelect
                          value={school}
                          onChange={onSchoolChange}
                          disabled={readOnly || pending || draftPending}
                          error={
                            fieldErrors.institutionId ||
                            fieldErrors.schoolCode ||
                            fieldErrors.code
                          }
                        />
                        <FieldMessage
                          message={
                            fieldErrors.institutionId ||
                            fieldErrors.schoolCode ||
                            fieldErrors.code
                          }
                        />
                        <button
                          type="button"
                          className="text-sm font-medium text-brand-blue underline-offset-2 hover:underline"
                          disabled={readOnly || pending || draftPending}
                          onClick={() => {
                            setSchoolManualMode(true);
                            setSchool(null);
                            setValue("affiliationType", "school");
                          }}
                          data-testid="school-not-listed"
                        >
                          School not listed?
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="space-y-2">
                          <Label htmlFor="organizationName">School name *</Label>
                          <Input
                            id="organizationName"
                            className="min-h-11"
                            value={values.organizationName ?? ""}
                            disabled={readOnly || pending || draftPending}
                            onChange={(e) =>
                              setValue("organizationName", e.target.value)
                            }
                            data-testid="manual-school-name"
                          />
                          <FieldMessage message={fieldErrors.organizationName} />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="regionId">Region *</Label>
                          <select
                            id="regionId"
                            className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            value={regionId}
                            disabled={readOnly || pending || draftPending}
                            onChange={(e) => setRegionId(e.target.value)}
                            aria-invalid={Boolean(fieldErrors.regionId)}
                            data-testid="region-select"
                          >
                            <option value="">Select region</option>
                            {regions.map((r) => (
                              <option key={r.regionId} value={r.regionId}>
                                {r.name}
                              </option>
                            ))}
                          </select>
                          <FieldMessage message={fieldErrors.regionId} />
                        </div>
                        <button
                          type="button"
                          className="text-sm font-medium text-brand-blue underline-offset-2 hover:underline"
                          disabled={readOnly || pending || draftPending}
                          onClick={() => {
                            setSchoolManualMode(false);
                            setValue("organizationName", "");
                            setRegionId("");
                          }}
                          data-testid="school-search-again"
                        >
                          Search school catalog instead
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2 sm:col-span-2">
                      <Label htmlFor="organizationName">
                        {affiliationType() === "company"
                          ? "Company name *"
                          : "Workshop name *"}
                      </Label>
                      <Input
                        id="organizationName"
                        className="min-h-11"
                        value={values.organizationName ?? ""}
                        disabled={readOnly || pending || draftPending}
                        onChange={(e) =>
                          setValue("organizationName", e.target.value)
                        }
                        data-testid="organization-name"
                      />
                      <FieldMessage message={fieldErrors.organizationName} />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="regionId">Region *</Label>
                      <select
                        id="regionId"
                        className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={regionId}
                        disabled={readOnly || pending || draftPending}
                        onChange={(e) => setRegionId(e.target.value)}
                        aria-invalid={Boolean(fieldErrors.regionId)}
                        data-testid="region-select"
                      >
                        <option value="">Select region</option>
                        {regions.map((r) => (
                          <option key={r.regionId} value={r.regionId}>
                            {r.name}
                          </option>
                        ))}
                      </select>
                      <FieldMessage message={fieldErrors.regionId} />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="organizationCity">City / town *</Label>
                      <Input
                        id="organizationCity"
                        className="min-h-11"
                        value={values.organizationCity ?? ""}
                        disabled={readOnly || pending || draftPending}
                        onChange={(e) =>
                          setValue("organizationCity", e.target.value)
                        }
                        data-testid="organization-city"
                      />
                      <FieldMessage message={fieldErrors.organizationCity} />
                    </div>
                  </div>
                )}

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="organizationPhone">Organisation phone *</Label>
                    <Input
                      id="organizationPhone"
                      type="tel"
                      className="min-h-11"
                      value={values.organizationPhone ?? ""}
                      disabled={readOnly || pending || draftPending}
                      onChange={(e) =>
                        setValue("organizationPhone", e.target.value)
                      }
                      data-testid="organization-phone"
                    />
                    <FieldMessage message={fieldErrors.organizationPhone} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="organizationEmail">Organisation email *</Label>
                    <Input
                      id="organizationEmail"
                      type="email"
                      className="min-h-11"
                      value={values.organizationEmail ?? ""}
                      disabled={readOnly || pending || draftPending}
                      onChange={(e) =>
                        setValue("organizationEmail", e.target.value)
                      }
                      data-testid="organization-email"
                    />
                    <FieldMessage message={fieldErrors.organizationEmail} />
                  </div>
                </div>
              </FormSection>
            )}

            {hasSkills ? (
              <FormSection
                icon={GraduationCap}
                title="Skill area"
                description={
                  mode === "institution"
                    ? "Choose a skill with remaining nomination quota for your school."
                    : formDef.maxSkills === 1
                      ? "Choose the skill you will compete in."
                      : `Select exactly ${formDef.maxSkills} skills.`
                }
              >
                {mode === "institution" && quotas.length > 0 ? (
                  <ul
                    className="mb-3 space-y-1 rounded-lg border border-border/70 bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                    data-testid="registration-quotas"
                  >
                    {quotas.map((q) => (
                      <li key={q.skillId}>
                        <span className="font-medium text-foreground">
                          {q.skillName}
                        </span>
                        {q.configured
                          ? `: ${q.remaining} of ${q.max} remaining`
                          : ": quota not configured"}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <fieldset
                  className="space-y-3"
                  data-testid="registration-skills"
                  disabled={readOnly || pending || draftPending}
                >
                  <legend className="sr-only">Skill selection</legend>
                  {skillIds.map((skillId, index) => (
                    <div key={index} className="flex gap-2">
                      <div className="min-w-0 flex-1 space-y-2">
                        <Label htmlFor={`skillIds-${index}`}>
                          {formDef.maxSkills > 1
                            ? `Skill ${index + 1}`
                            : "Skill *"}
                        </Label>
                        <select
                          id={`skillIds-${index}`}
                          className="flex min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          value={skillId}
                          aria-invalid={Boolean(fieldErrors.skillIds)}
                          onChange={(e) =>
                            updateSkillAt(index, e.target.value)
                          }
                          data-testid={`skill-id-${index}`}
                        >
                          <option value="">Select a skill</option>
                          {skills.map((s) => {
                            const quota = quotaBySkill[s.skillId];
                            const exhausted =
                              mode === "institution" &&
                              quota != null &&
                              (!quota.configured || quota.remaining <= 0);
                            return (
                              <option
                                key={s.skillId}
                                value={s.skillId}
                                disabled={exhausted}
                              >
                                {s.number ? `${s.number} — ` : ""}
                                {s.name}
                                {s.familyName ? ` (${s.familyName})` : ""}
                                {mode === "institution" && quota?.configured
                                  ? ` — ${quota.remaining} left`
                                  : ""}
                                {exhausted ? " (quota full)" : ""}
                              </option>
                            );
                          })}
                        </select>
                      </div>
                      {formDef.maxSkills > 1 && skillIds.length > 1 ? (
                        <Button
                          type="button"
                          variant="outline"
                          className="mt-7 min-h-11 shrink-0"
                          onClick={() => removeSkillSlot(index)}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </div>
                  ))}
                  {formDef.maxSkills > 1 ? (
                    <Button
                      type="button"
                      variant="secondary"
                      className="min-h-11"
                      disabled={skillIds.length >= formDef.maxSkills}
                      onClick={addSkillSlot}
                      data-testid="skill-add"
                    >
                      Add skill
                    </Button>
                  ) : null}
                  <FieldMessage
                    id="skillIds-error"
                    message={fieldErrors.skillIds}
                  />
                </fieldset>
              </FormSection>
            ) : null}
              </>
            )}

            {currentStep === 4 && (
            <FormSection
              icon={UserRound}
              title="Coach / team leader"
              description="BIO-DATA OF TEAM LEADER/COACH/COMPATRIOT EXPERT OF THE COMPETITOR FROM THE COMPETING INSTITUTION"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                {(
                  [
                    { key: "surname", label: "Surname", required: true },
                    { key: "firstName", label: "First name", required: true },
                    { key: "otherName", label: "Other name", required: false },
                    {
                      key: "contactNumber",
                      label: "Contact number",
                      required: true,
                      type: "tel",
                    },
                    {
                      key: "email",
                      label: "Email address",
                      required: true,
                      type: "email",
                    },
                    {
                      key: "whatsapp",
                      label: "WhatsApp line / contact",
                      required: true,
                      type: "tel",
                    },
                    {
                      key: "dateOfBirth",
                      label: "Date of birth",
                      required: true,
                      type: "date",
                      wide: true,
                    },
                  ] as const
                ).map((field) => {
                  const errKey = `coach.${field.key}`;
                  const err = fieldErrors[errKey] || fieldErrors.coach;
                  return (
                    <div
                      key={field.key}
                      className={cn(
                        "space-y-2",
                        "wide" in field && field.wide ? "sm:col-span-2" : null,
                      )}
                    >
                      <Label htmlFor={`coach-${field.key}`}>
                        {field.label}
                        {field.required ? " *" : ""}
                      </Label>
                      <Input
                        id={`coach-${field.key}`}
                        name={errKey}
                        type={"type" in field ? field.type : "text"}
                        className="min-h-11"
                        required={field.required}
                        value={coach[field.key]}
                        disabled={readOnly || pending || draftPending}
                        aria-invalid={Boolean(err)}
                        data-testid={`coach-${field.key}`}
                        onChange={(e) => {
                          const value = e.target.value;
                          setCoach((prev) => ({ ...prev, [field.key]: value }));
                          setFieldErrors((prev) => {
                            const next = { ...prev };
                            delete next[errKey];
                            delete next.coach;
                            return next;
                          });
                        }}
                        autoComplete="off"
                      />
                      <FieldMessage message={err} />
                    </div>
                  );
                })}
              </div>
            </FormSection>
            )}

            {currentStep === 5 && (
            <FormSection
              icon={ShieldCheck}
              title="Confirm & submit"
              description="Review your details before submitting. You will receive a competitor reference on success."
            >
              <dl
                className="space-y-3 rounded-lg border border-border/70 bg-muted/30 px-4 py-3 text-sm"
                data-testid="registration-review-summary"
              >
                <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                  <dt className="text-muted-foreground">Name</dt>
                  <dd className="font-medium text-foreground sm:text-right">
                    {summaryName}
                  </dd>
                </div>
                <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                  <dt className="text-muted-foreground">Skill</dt>
                  <dd className="font-medium text-foreground sm:text-right">
                    {summarySkill}
                  </dd>
                </div>
                <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                  <dt className="text-muted-foreground">Affiliation</dt>
                  <dd className="font-medium text-foreground sm:text-right">
                    {summarySchool}
                  </dd>
                </div>
                <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                  <dt className="text-muted-foreground">ID</dt>
                  <dd className="font-medium text-foreground sm:text-right">
                    {summaryId}
                  </dd>
                </div>
                {values.heardAbout ? (
                  <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                    <dt className="text-muted-foreground">Heard about WSGH</dt>
                    <dd className="font-medium text-foreground sm:text-right">
                      {values.heardAbout}
                    </dd>
                  </div>
                ) : null}
                {mode === "competitor" && values.guardianName ? (
                  <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
                    <dt className="text-muted-foreground">Guardian</dt>
                    <dd className="font-medium text-foreground sm:text-right">
                      {values.guardianName}
                      {values.guardianPhone
                        ? ` · ${values.guardianPhone}`
                        : ""}
                    </dd>
                  </div>
                ) : null}
              </dl>

              {hasDeclaration ? (
                <div className="space-y-2">
                  <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 px-3 py-3">
                    <input
                      id="declarationAccepted"
                      type="checkbox"
                      className="mt-1 size-4 accent-brand-blue"
                      checked={declarationAccepted}
                      disabled={readOnly || pending || draftPending}
                      aria-invalid={Boolean(fieldErrors.declarationAccepted)}
                      onChange={(e) =>
                        setDeclarationAccepted(e.target.checked)
                      }
                      data-testid="registration-declaration"
                    />
                    <Label htmlFor="declarationAccepted" className="font-normal leading-relaxed">
                      I declare that the information provided is accurate and I
                      accept the competition rules.
                    </Label>
                  </div>
                  <FieldMessage
                    id="declarationAccepted-error"
                    message={fieldErrors.declarationAccepted}
                  />
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="captchaToken">Security check *</Label>
                <Input
                  id="captchaToken"
                  className="min-h-11"
                  value={captchaToken}
                  disabled={readOnly || pending || draftPending}
                  onChange={(e) => setCaptchaToken(e.target.value)}
                  autoComplete="off"
                  data-testid="registration-captcha"
                />
                <FieldMessage
                  id="captchaToken-error"
                  message={fieldErrors.captchaToken}
                />
              </div>

              <div
                data-testid={
                  error?.code === "ABUSE_SUSPECTED"
                    ? "registration-abuse-alert"
                    : undefined
                }
              >
                <ApiErrorAlert
                  error={error}
                  title="Could not submit registration"
                />
              </div>
            </FormSection>
            )}

            {error && currentStep < 5 ? (
              <ApiErrorAlert
                error={error}
                title="Could not save progress"
              />
            ) : null}

            <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border/80 bg-white/90 px-4 py-3 backdrop-blur-md sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
              <div className="mx-auto flex max-w-2xl flex-col gap-2 sm:mx-0 sm:flex-row sm:flex-wrap">
                {currentStep > 1 ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-12 flex-1 gap-2 text-base sm:flex-none sm:min-w-28"
                    disabled={pending || draftPending}
                    onClick={() => setCurrentStep(clampStep(currentStep - 1))}
                    data-testid="registration-back"
                  >
                    Back
                  </Button>
                ) : null}
                {mode === "competitor" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    className="min-h-12 flex-1 gap-2 text-base sm:flex-none sm:min-w-32"
                    disabled={pending || draftPending || readOnly}
                    onClick={() => void handleSaveDraftClick()}
                    data-testid="registration-save-draft"
                  >
                    {draftPending ? "Saving…" : "Save draft"}
                  </Button>
                ) : null}
                {currentStep < 5 ? (
                  <Button
                    type="button"
                    className="min-h-12 w-full flex-1 gap-2 text-base sm:min-w-40"
                    disabled={pending || draftPending || readOnly}
                    onClick={() => void handleContinue()}
                    data-testid="registration-continue"
                  >
                    {draftPending ? "Saving…" : "Continue"}
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    className="min-h-12 w-full flex-1 gap-2 text-base sm:min-w-40"
                    disabled={pending || draftPending || readOnly}
                    data-testid="registration-submit"
                  >
                    {pending ? (
                      "Submitting…"
                    ) : readOnly ? (
                      "Registration closed"
                    ) : (
                      <>
                        <CheckCircle2 className="size-4" aria-hidden />
                        Submit registration
                      </>
                    )}
                  </Button>
                )}
              </div>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  );
}
