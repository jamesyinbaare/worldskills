/** Passthrough — public register routes sit here; RoleGate lives under (portal). */
export default function CompetitorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
