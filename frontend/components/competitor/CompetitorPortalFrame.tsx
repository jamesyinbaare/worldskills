"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { CompetitorShell } from "@/components/competitor/CompetitorShell";
import {
  ApiError,
  listMyRegistrations,
  type MyRegistrationOut,
} from "@/lib/api";

type CompetitorPortalFrameProps = {
  children: ReactNode;
};

function isRegistrationFlowPath(pathname: string): boolean {
  return pathname.includes("/register");
}

/**
 * Wraps competitor portal pages in the sidenav shell.
 * Registration/confirmation keep a cleaner full-width layout (no sidebar).
 */
export function CompetitorPortalFrame({ children }: CompetitorPortalFrameProps) {
  const pathname = usePathname();
  const [registrations, setRegistrations] = useState<MyRegistrationOut[] | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await listMyRegistrations();
        if (!cancelled) setRegistrations(rows);
      } catch (err) {
        if (!cancelled) {
          setRegistrations([]);
          if (!(err instanceof ApiError)) {
            /* ignore — pages can still render */
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (isRegistrationFlowPath(pathname)) {
    return <>{children}</>;
  }

  if (registrations === null) {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center px-4 py-12">
        <p className="text-sm text-muted-foreground" role="status">
          Loading your competitions…
        </p>
      </div>
    );
  }

  return (
    <CompetitorShell registrations={registrations}>{children}</CompetitorShell>
  );
}
