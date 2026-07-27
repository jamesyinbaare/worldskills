"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CompetitionRegistrationForm } from "@/components/registration/CompetitionRegistrationForm";

function CompetitorRegisterForm() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;

  return (
    <CompetitionRegistrationForm
      competitionId={competitionId}
      mode="competitor"
      backHref="/competitor"
      confirmationHref={`/competitor/competitions/${competitionId}/register/confirmation`}
    />
  );
}

export default function CompetitorRegisterPage() {
  return (
    <Suspense
      fallback={
        <div className="bg-competitions-atmosphere min-h-[calc(100dvh-var(--site-header-height))]">
          <div className="mx-auto max-w-2xl px-4 py-16 text-sm text-muted-foreground">
            Loading registration…
          </div>
        </div>
      }
    >
      <CompetitorRegisterForm />
    </Suspense>
  );
}
