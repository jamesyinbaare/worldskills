export default function InstitutionRootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Register routes sit outside (portal) without RoleGate here —
  // CompetitionRegistrationForm enforces institution auth.
  return <>{children}</>;
}
