"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  CatalogSkillOut,
  CreateUserResponse,
  InstitutionListItem,
  createUser,
  isSuperAdminRole,
  listCatalogSkills,
  listInstitutions,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  GHANA_PHONE_FIELD_HINT,
  ghanaPhoneFieldError,
  requiredGhanaPhoneError,
} from "@/lib/phone";

const BASE_ROLES = [
  { value: "EXPERT", label: "Expert" },
  { value: "CHIEF_EXPERT", label: "Chief expert" },
  { value: "MODERATOR", label: "Moderator" },
  { value: "APPEALS_OFFICER", label: "Appeals officer" },
];

const NO_INSTITUTION = "__none__";

function skillLabel(skill: CatalogSkillOut) {
  return skill.number ? `${skill.name} (${skill.number})` : skill.name;
}

export default function NewUserPage() {
  const router = useRouter();
  const { me } = useAuth();
  const roleOptions = useMemo(() => {
    const opts = [...BASE_ROLES];
    if (me && isSuperAdminRole(me.role)) {
      opts.unshift({ value: "ADMIN", label: "Administrator" });
    }
    return opts;
  }, [me]);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [role, setRole] = useState("EXPERT");
  const [institutionId, setInstitutionId] = useState(NO_INSTITUTION);
  const [credentialMode, setCredentialMode] = useState<"TEMP_PASSWORD" | "INVITE">(
    "INVITE",
  );
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [institutions, setInstitutions] = useState<InstitutionListItem[]>([]);
  const [catalogSkills, setCatalogSkills] = useState<CatalogSkillOut[]>([]);
  const [catalogSkillIds, setCatalogSkillIds] = useState<string[]>([]);
  const [created, setCreated] = useState<CreateUserResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const expertRole = role === "EXPERT" || role === "CHIEF_EXPERT";

  const skillsByFamily = useMemo(() => {
    const map = new Map<string, { familyName: string; skills: CatalogSkillOut[] }>();
    for (const skill of catalogSkills) {
      const key = skill.familyId;
      const bucket = map.get(key) ?? {
        familyName: skill.familyName ?? "Family",
        skills: [],
      };
      bucket.skills.push(skill);
      map.set(key, bucket);
    }
    return Array.from(map.values()).sort((a, b) =>
      a.familyName.localeCompare(b.familyName),
    );
  }, [catalogSkills]);

  useEffect(() => {
    void listInstitutions()
      .then(setInstitutions)
      .catch(() => setInstitutions([]));
    void listCatalogSkills({ active: true })
      .then(setCatalogSkills)
      .catch(() => setCatalogSkills([]));
  }, []);

  function toggleSkill(skillId: string, checked: boolean) {
    setCatalogSkillIds((prev) =>
      checked ? [...prev, skillId] : prev.filter((id) => id !== skillId),
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const phoneErr = requiredGhanaPhoneError(phoneNumber);
    if (phoneErr) {
      setFieldErrors({ phoneNumber: phoneErr });
      return;
    }
    setFieldErrors({});
    setCreated(null);
    setPending(true);
    try {
      const out = await createUser({
        email: email.trim(),
        fullName: fullName.trim(),
        phoneNumber: phoneNumber.trim(),
        role,
        institutionId:
          expertRole && institutionId !== NO_INSTITUTION
            ? institutionId
            : undefined,
        credentialMode,
        temporaryPassword:
          credentialMode === "TEMP_PASSWORD" ? temporaryPassword : undefined,
        catalogSkillIds: expertRole ? catalogSkillIds : undefined,
      });
      setCreated(out);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="New staff account"
        description="Send an email invite or set a temporary password the user must change on first sign-in."
        backHref="/admin/users"
        backLabel="Staff accounts"
      />

      {created ? (
        <Alert data-testid="user-created">
          <AlertTitle>Account created</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              {created.fullName} ({created.email}) — {created.role}
            </p>
            {created.temporaryPassword ? (
              <p className="font-mono text-sm break-all">
                Temporary password (shown once): {created.temporaryPassword}
              </p>
            ) : null}
            {created.inviteSent ? (
              <p className="text-sm">Invitation email sent.</p>
            ) : null}
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => router.push(`/admin/users/${created.userId}`)}
            >
              Open account
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <Card>
          <CardHeader className="px-4 sm:px-6">
            <CardDescription>
              Competitor and institution logins use self-registration (not created here).
            </CardDescription>
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="fullName">Full name</Label>
                <Input
                  id="fullName"
                  required
                  className="min-h-11"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  className="min-h-11"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <FieldMessage message={fieldErrors.email} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phoneNumber">Phone number</Label>
                <Input
                  id="phoneNumber"
                  type="tel"
                  inputMode="tel"
                  required
                  className="min-h-11"
                  placeholder="e.g. 0551234567"
                  value={phoneNumber}
                  onChange={(e) => {
                    const next = e.target.value;
                    setPhoneNumber(next);
                    setFieldErrors((prev) => {
                      const phoneErr = ghanaPhoneFieldError(next);
                      if (!phoneErr && !prev.phoneNumber) return prev;
                      const copy = { ...prev };
                      if (phoneErr) copy.phoneNumber = phoneErr;
                      else delete copy.phoneNumber;
                      return copy;
                    });
                  }}
                  onBlur={() => {
                    const phoneErr = ghanaPhoneFieldError(phoneNumber);
                    setFieldErrors((prev) => {
                      if (!phoneErr && !prev.phoneNumber) return prev;
                      const copy = { ...prev };
                      if (phoneErr) copy.phoneNumber = phoneErr;
                      else delete copy.phoneNumber;
                      return copy;
                    });
                  }}
                  aria-invalid={Boolean(fieldErrors.phoneNumber)}
                />
                <p className="text-xs text-muted-foreground">
                  {GHANA_PHONE_FIELD_HINT}
                </p>
                <FieldMessage message={fieldErrors.phoneNumber} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Role</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger id="role" className="min-h-11 w-full">
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                  <SelectContent>
                    {roleOptions.map((r) => (
                      <SelectItem key={r.value} value={r.value}>
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {expertRole ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="institutionId">Institution (COI, optional)</Label>
                    <Select value={institutionId} onValueChange={setInstitutionId}>
                      <SelectTrigger id="institutionId" className="min-h-11 w-full">
                        <SelectValue placeholder="Select institution" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NO_INSTITUTION}>None</SelectItem>
                        {institutions.map((i) => (
                          <SelectItem key={i.institutionId} value={i.institutionId}>
                            {i.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldMessage message={fieldErrors.institutionId} />
                  </div>
                  <div className="space-y-2">
                    <Label>Skill areas</Label>
                    <p className="text-xs text-muted-foreground">
                      Experts are global — pick one or more catalog skill areas
                      (including multiple under the same family).
                    </p>
                    {skillsByFamily.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No active catalog skill areas yet.
                      </p>
                    ) : (
                      <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border border-border p-3">
                        {skillsByFamily.map((group) => (
                          <div key={group.familyName} className="space-y-2">
                            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                              {group.familyName}
                            </p>
                            {group.skills.map((skill) => {
                              const checked = catalogSkillIds.includes(skill.skillId);
                              const inputId = `create-skill-${skill.skillId}`;
                              return (
                                <label
                                  key={skill.skillId}
                                  htmlFor={inputId}
                                  className="flex cursor-pointer items-start gap-2.5 text-sm"
                                >
                                  <Checkbox
                                    id={inputId}
                                    checked={checked}
                                    onCheckedChange={(value) =>
                                      toggleSkill(skill.skillId, value === true)
                                    }
                                    className="mt-0.5"
                                  />
                                  <span>{skillLabel(skill)}</span>
                                </label>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    )}
                    <FieldMessage message={fieldErrors.catalogSkillIds} />
                  </div>
                </>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="credentialMode">Credentials</Label>
                <Select
                  value={credentialMode}
                  onValueChange={(v) =>
                    setCredentialMode(v as "TEMP_PASSWORD" | "INVITE")
                  }
                >
                  <SelectTrigger id="credentialMode" className="min-h-11 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="INVITE">Email invite</SelectItem>
                    <SelectItem value="TEMP_PASSWORD">Temporary password</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {credentialMode === "TEMP_PASSWORD" ? (
                <div className="space-y-2">
                  <Label htmlFor="temporaryPassword">Temporary password</Label>
                  <Input
                    id="temporaryPassword"
                    type="password"
                    required
                    minLength={8}
                    className="min-h-11"
                    value={temporaryPassword}
                    onChange={(e) => setTemporaryPassword(e.target.value)}
                  />
                </div>
              ) : null}
              <ApiErrorAlert error={error} title="Could not create account" />
              <Button type="submit" className="min-h-11 w-full" disabled={pending}>
                {pending ? "Creating…" : "Create account"}
              </Button>
              <Button variant="link" className="min-h-11 px-0" asChild>
                <Link href="/admin/users">Cancel</Link>
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </PageShell>
  );
}
