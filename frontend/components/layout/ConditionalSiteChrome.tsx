"use client";

import { usePathname } from "next/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";

function isCompetitorPortalPath(pathname: string): boolean {
  if (!pathname.startsWith("/competitor")) return false;
  // Public registration flow keeps the global site chrome
  if (pathname.includes("/register")) return false;
  return true;
}

function isInstitutionPortalPath(pathname: string): boolean {
  if (!pathname.startsWith("/institution")) return false;
  if (pathname.includes("/register")) return false;
  return true;
}

export function ConditionalSiteHeader() {
  const pathname = usePathname();
  if (pathname.startsWith("/admin")) return null;
  if (isCompetitorPortalPath(pathname)) return null;
  if (isInstitutionPortalPath(pathname)) return null;
  return <SiteHeader />;
}
