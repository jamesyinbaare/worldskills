"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CompetitionRegistrationForm } from "@/components/registration/CompetitionRegistrationForm";

function InstitutionRegisterForm() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;

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
