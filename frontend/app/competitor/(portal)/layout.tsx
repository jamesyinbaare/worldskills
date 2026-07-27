import { RoleGate } from "@/components/auth/RoleGate";
import { CompetitorPortalFrame } from "@/components/competitor/CompetitorPortalFrame";

export default function CompetitorPortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RoleGate roles="competitor">
      <CompetitorPortalFrame>{children}</CompetitorPortalFrame>
    </RoleGate>
  );
}
