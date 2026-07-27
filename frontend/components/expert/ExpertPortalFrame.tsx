"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ExpertShell } from "@/components/expert/ExpertShell";
import {
  ApiError,
  listMyAssignments,
  type MyAssignmentOut,
} from "@/lib/api";

type ExpertPortalFrameProps = {
  children: ReactNode;
};

/**
 * Loads the expert's assignments and wraps portal pages in a sidenav
 * shell when they have at least one assignment.
 */
export function ExpertPortalFrame({ children }: ExpertPortalFrameProps) {
  const [assignments, setAssignments] = useState<MyAssignmentOut[] | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyAssignments();
        if (!cancelled) {
          setAssignments(rows);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setAssignments([]);
          if (err instanceof ApiError) setError(err);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (assignments === null) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center px-4 py-12">
        <p className="text-sm text-muted-foreground" role="status">
          Loading your assignments…
        </p>
      </div>
    );
  }

  if (error && assignments.length === 0) {
    // Fall through to hub without shell; pages can still work / show errors.
  }

  if (assignments.length > 0) {
    return (
      <ExpertShell assignments={assignments}>{children}</ExpertShell>
    );
  }

  return <>{children}</>;
}
