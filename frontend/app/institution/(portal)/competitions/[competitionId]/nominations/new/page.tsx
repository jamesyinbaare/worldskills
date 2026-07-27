"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  type RegionOut,
  createNomination,
  listRegions,
} from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { upsertNomination } from "@/lib/nominationStore";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function NewNominationPage() {
  const router = useRouter();
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const { me } = useAuth();

  const [institutionId, setInstitutionId] = useState("");
  const [skillId, setSkillId] = useState("");
  const [competitorRef, setCompetitorRef] = useState("");
  const [regionId, setRegionId] = useState("");
  const [regions, setRegions] = useState<RegionOut[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const fromSession = me?.institutionId ?? me?.institution_id;
    if (fromSession && !institutionId) {
      setInstitutionId(fromSession);
    }
  }, [me, institutionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listRegions();
        if (!cancelled) setRegions(list.filter((r) => r.active));
      } catch {
        // Region list is optional UX; institution home region still applies server-side.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const out = await createNomination(competitionId, {
        institutionId: institutionId.trim(),
        skillId: skillId.trim(),
        competitorRef: competitorRef.trim(),
        regionId: regionId.trim() || null,
      });
      upsertNomination(competitionId, {
        nominationId: out.nominationId,
        status: out.status,
        skillId: skillId.trim(),
        competitorRef: competitorRef.trim(),
        institutionId: institutionId.trim(),
        reason: out.reason ?? null,
      });
      router.push(`/institution/competitions/${competitionId}/nominations`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not submit nomination",
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

  return (
    <PageShell width="narrow" className="space-y-6">
      <PageHeader
        title="Nominate competitor"
        description="Submit a nomination for an eligible skill within your limit."
        backHref={`/institution/competitions/${competitionId}/nominations`}
        backLabel="Nominations"
      />

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardDescription>
            Institution, skill, and competitor reference are required. Region
            override is optional (defaults to the institution home region).
          </CardDescription>
        </CardHeader>
        <CardContent className="px-4 sm:px-6">
          <form
            onSubmit={onSubmit}
            className="space-y-4"
            noValidate
            data-testid="nomination-form"
          >
            <div className="space-y-2">
              <Label htmlFor="institutionId">Institution ID</Label>
              <Input
                id="institutionId"
                className="min-h-11"
                required
                value={institutionId}
                aria-invalid={Boolean(fieldErrors.institutionId)}
                aria-describedby={
                  fieldErrors.institutionId ? "institutionId-error" : undefined
                }
                onChange={(e) => setInstitutionId(e.target.value)}
              />
              <FieldMessage
                id="institutionId-error"
                message={fieldErrors.institutionId}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skillId">Skill ID</Label>
              <Input
                id="skillId"
                className="min-h-11"
                required
                value={skillId}
                aria-invalid={Boolean(fieldErrors.skillId)}
                aria-describedby={
                  fieldErrors.skillId ? "skillId-error" : undefined
                }
                onChange={(e) => setSkillId(e.target.value)}
              />
              <FieldMessage id="skillId-error" message={fieldErrors.skillId} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="competitorRef">Competitor reference</Label>
              <Input
                id="competitorRef"
                className="min-h-11"
                required
                value={competitorRef}
                aria-invalid={Boolean(fieldErrors.competitorRef)}
                aria-describedby={
                  fieldErrors.competitorRef ? "competitorRef-error" : undefined
                }
                onChange={(e) => setCompetitorRef(e.target.value)}
              />
              <FieldMessage
                id="competitorRef-error"
                message={fieldErrors.competitorRef}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="regionId">Region override (optional)</Label>
              <Select
                value={regionId || undefined}
                onValueChange={(v) => setRegionId(v ?? "")}
              >
                <SelectTrigger id="regionId" className="min-h-11 w-full">
                  <SelectValue placeholder="Use institution home region" />
                </SelectTrigger>
                <SelectContent>
                  {regions.map((r) => (
                    <SelectItem key={r.regionId} value={r.regionId}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldMessage message={fieldErrors.regionId} />
            </div>
            <ApiErrorAlert error={error} title="Could not submit nomination" />
            <Button
              type="submit"
              className="min-h-11 w-full"
              disabled={pending}
              data-testid="nomination-submit"
            >
              {pending ? "Submitting…" : "Submit nomination"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}
