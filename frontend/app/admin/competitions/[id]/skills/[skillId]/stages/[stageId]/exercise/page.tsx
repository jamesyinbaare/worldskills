"use client";

import { useParams } from "next/navigation";
import { StageExerciseEditor } from "@/components/admin/StageExerciseEditor";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";

export default function StageExerciseEditorPage() {
  const params = useParams<{
    id: string;
    skillId: string;
    stageId: string;
  }>();
  const competitionId = params.id;
  const skillId = params.skillId;
  const stageId = params.stageId;

  return (
    <PageShell className="space-y-6">
      <PageHeader
        title="Stage exercise"
        description="Challenge brief, deliverables, and marking scheme for this stage."
        backHref={`/admin/competitions/${competitionId}/skills/${skillId}/pathway`}
        backLabel="Stage pathway"
      />
      <StageExerciseEditor competitionId={competitionId} stageId={stageId} />
    </PageShell>
  );
}
