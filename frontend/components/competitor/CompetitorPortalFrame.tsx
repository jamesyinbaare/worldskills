"use client";

import { useEffect, useState, type ReactNode } from "react";
import { CompetitorShell } from "@/components/competitor/CompetitorShell";
import {
  ApiError,
  listMyRegistrations,
  type MyRegistrationOut,
} from "@/lib/api";

type CompetitorPortalFrameProps = {
  children: ReactNode;
};

/**
 * Loads the competitor's registrations and wraps portal pages in a sidenav
 * shell when they have at least one registration.
 */
export function CompetitorPortalFrame({ children }: CompetitorPortalFrameProps) {
  const [registrations, setRegistrations] = useState<MyRegistrationOut[] | null>(
    null,
  );
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (!cancelled) {
          setRegistrations(rows);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setRegistrations([]);
          if (err instanceof ApiError) setError(err);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (registrations === null) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center px-4 py-12">
        <p className="text-sm text-muted-foreground" role="status">
          Loading your competitions…
        </p>
      </div>
    );
  }

  if (error && registrations.length === 0) {
    // Fall through to hub without shell; pages can still work / show errors.
  }

  if (registrations.length > 0) {
    return (
      <CompetitorShell registrations={registrations}>{children}</CompetitorShell>
    );
  }

  return <>{children}</>;
}
