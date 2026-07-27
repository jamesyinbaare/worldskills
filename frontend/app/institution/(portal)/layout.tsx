import { RoleGate } from "@/components/auth/RoleGate";
import { InstitutionPortalFrame } from "@/components/institution/InstitutionPortalFrame";

export default function InstitutionPortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RoleGate roles="institution">
      <InstitutionPortalFrame>{children}</InstitutionPortalFrame>
    </RoleGate>
  );
}
