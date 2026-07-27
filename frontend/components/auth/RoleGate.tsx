"use client";

import { useLayoutEffect, type ReactNode } from "react";
import { useAuth, useRequireRole } from "@/components/auth/AuthProvider";
import type { AppRole } from "@/lib/api";

type RoleGateProps = {
  roles: AppRole | AppRole[];
  children: ReactNode;
};

/** Client gate for role-scoped route trees — mobile-first loading/redirect. */
export function RoleGate({ roles, children }: RoleGateProps) {
  const { status } = useAuth();
  const { ready, loading } = useRequireRole(roles);

  useLayoutEffect(() => {
    if (status !== "anonymous") return;
    if (window.location.pathname.startsWith("/login")) return;
    // Prefer assign + href for environments that no-op replace during hydration.
    window.location.assign("/login");
  }, [status]);

  if (loading || status === "loading") {
    return (
      <div className="flex min-h-[50dvh] items-center justify-center px-4 py-12">
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      </div>
    );
  }

  if (status === "anonymous" || !ready) {
    return (
      <div className="flex min-h-[50dvh] flex-col items-center justify-center gap-3 px-4 py-12">
        <p className="text-sm text-muted-foreground" role="status">
          Loading…
        </p>
        {/* Noscript / fallback if client redirect is blocked */}
        <a className="text-sm font-medium text-primary underline" href="/login">
          Sign in
        </a>
      </div>
    );
  }

  return <>{children}</>;
}
