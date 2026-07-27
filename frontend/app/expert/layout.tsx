import { RoleGate } from "@/components/auth/RoleGate";
import { ExpertPortalFrame } from "@/components/expert/ExpertPortalFrame";

export default function ExpertLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RoleGate roles="expert">
      <ExpertPortalFrame>{children}</ExpertPortalFrame>
    </RoleGate>
  );
}
