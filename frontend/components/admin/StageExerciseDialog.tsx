"use client";

import { StageExerciseEditor } from "@/components/admin/StageExerciseEditor";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type StageExerciseDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  competitionId: string;
  stageId: string;
  stageLabel?: string;
  onStatusChange?: (status: string | null) => void;
};

export function StageExerciseDialog({
  open,
  onOpenChange,
  competitionId,
  stageId,
  stageLabel,
  onStatusChange,
}: StageExerciseDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="shrink-0 border-b border-border px-6 py-4 pr-12">
          <DialogTitle>
            {stageLabel ? `${stageLabel} exercise` : "Stage exercise"}
          </DialogTitle>
          <DialogDescription>
            Challenge brief, deliverables, and marking scheme for this stage.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {open && stageId ? (
            <StageExerciseEditor
              key={stageId}
              competitionId={competitionId}
              stageId={stageId}
              onStatusChange={onStatusChange}
            />
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
