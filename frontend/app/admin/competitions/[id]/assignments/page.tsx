"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { Skeleton } from "@/components/ui/skeleton";

export default function AssignmentsRedirectPage() {
  const params = useParams<{ id: string }>();
  const competitionId = params.id;
  const router = useRouter();

  useEffect(() => {
    router.replace(`/admin/competitions/${competitionId}/skills`);
  }, [competitionId, router]);

  return (
    <PageShell>
      <div className="space-y-3" role="status" aria-label="Redirecting">
        <Skeleton className="h-8 w-2/3" />
        <p className="text-sm text-muted-foreground">
          Expert assignments are managed on each skill. Redirecting to skills…
        </p>
      </div>
    </PageShell>
  );
}
