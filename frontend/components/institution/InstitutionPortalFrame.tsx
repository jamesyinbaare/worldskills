"use client";

import type { ReactNode } from "react";
import { InstitutionShell } from "@/components/institution/InstitutionShell";

type InstitutionPortalFrameProps = {
  children: ReactNode;
};

export function InstitutionPortalFrame({
  children,
}: InstitutionPortalFrameProps) {
  return <InstitutionShell>{children}</InstitutionShell>;
}
