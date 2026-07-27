"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  type AppRole,
  type Me,
  clearTokens,
  fetchMe,
  getAccessToken,
  homeForRole,
  logout as clearSession,
  roleMatches,
} from "@/lib/api";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: AuthStatus;
  me: Me | null;
  refresh: () => Promise<Me | null>;
  logout: () => void;
  requireRole: (roles: AppRole | AppRole[]) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  // Start loading so RoleGate waits for token bootstrap before redirecting.
  const [status, setStatus] = useState<AuthStatus>("loading");
  const router = useRouter();

  const refresh = useCallback(async () => {
    if (!getAccessToken()) {
      setMe(null);
      setStatus("anonymous");
      return null;
    }
    setStatus("loading");
    try {
      const user = await fetchMe();
      setMe(user);
      setStatus("authenticated");
      return user;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearTokens();
      }
      setMe(null);
      setStatus("anonymous");
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      if (!getAccessToken()) {
        if (!cancelled) {
          setMe(null);
          setStatus("anonymous");
        }
        return;
      }
      try {
        const user = await fetchMe();
        if (!cancelled) {
          setMe(user);
          setStatus("authenticated");
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          clearTokens();
        }
        if (!cancelled) {
          setMe(null);
          setStatus("anonymous");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setMe(null);
    setStatus("anonymous");
    router.push("/login");
  }, [router]);

  const requireRole = useCallback(
    (roles: AppRole | AppRole[]) => {
      if (!me) return false;
      return roleMatches(me.role, roles);
    },
    [me],
  );

  const value = useMemo(
    () => ({ status, me, refresh, logout, requireRole }),
    [status, me, refresh, logout, requireRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

/** Client guard: redirect anonymous → login, wrong role → home. */
export function useRequireRole(roles: AppRole | AppRole[], redirectTo = "/login") {
  const { status, me, requireRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;
    if (status === "anonymous") {
      if (!window.location.pathname.startsWith(redirectTo)) {
        window.location.assign(redirectTo);
      }
      return;
    }
    if (me && !requireRole(roles)) {
      router.replace(homeForRole(me.role));
    }
  }, [status, me, requireRole, roles, router, redirectTo]);

  return {
    ready: status === "authenticated" && !!me && requireRole(roles),
    loading: status === "loading",
    me,
  };
}
