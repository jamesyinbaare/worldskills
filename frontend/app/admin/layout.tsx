import { RoleGate } from "@/components/auth/RoleGate";
import { AdminShell } from "@/components/admin/AdminShell";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RoleGate roles="admin">
      <AdminShell>{children}</AdminShell>
    </RoleGate>
  );
}
