"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { Skeleton } from "@/components/ui/skeleton";

export default function CycleMarkingSchemesRedirectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const competitionId = params.id;

  useEffect(() => {
    router.replace(`/admin/competitions/${competitionId}/skills`);
  }, [competitionId, router]);

  return (
    <PageShell>
      <div className="space-y-3" role="status" aria-label="Redirecting">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <p className="text-sm text-muted-foreground">
          Rubrics are configured on each stage exercise. Redirecting to skills…
        </p>
      </div>
    </PageShell>
  );
}
