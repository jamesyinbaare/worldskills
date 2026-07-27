import { redirect } from "next/navigation";

export default async function LegacyNominationsRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/admin/competitors?competitionId=${encodeURIComponent(id)}`);
}
