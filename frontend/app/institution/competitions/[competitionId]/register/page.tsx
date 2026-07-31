"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, getPublicSettings } from "@/lib/api";
import { CompetitionRegistrationForm } from "@/components/registration/CompetitionRegistrationForm";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

function InstitutionRegisterForm() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const settings = await getPublicSettings();
        if (!cancelled) {
          setEnabled(settings.institutionRegistrationEnabled);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setEnabled(false);
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load registration settings.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (enabled === null) {
    return (
      <p className="mx-auto max-w-xl px-4 py-16 text-sm text-muted-foreground" role="status">
        Loading registration…
      </p>
    );
  }

  if (!enabled) {
    return (
      <div className="mx-auto max-w-xl space-y-6 px-4 py-16">
        <Alert>
          <AlertTitle>Institution registration unavailable</AlertTitle>
          <AlertDescription>
            {error ??
              "Schools cannot register competitors on behalf of students at this time. Competitors may register individually when the competition is open."}
          </AlertDescription>
        </Alert>
        <Button variant="outline" className="min-h-11" asChild>
          <Link href="/institution">Back to institution portal</Link>
        </Button>
      </div>
    );
  }

  return (
    <CompetitionRegistrationForm
      competitionId={competitionId}
      mode="institution"
      backHref="/institution"
      confirmationHref={`/institution/competitions/${competitionId}/register/confirmation`}
    />
  );
}

export default function InstitutionRegisterPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-xl px-4 py-16 text-sm text-muted-foreground">
          Loading registration…
        </div>
      }
    >
      <InstitutionRegisterForm />
    </Suspense>
  );
}
