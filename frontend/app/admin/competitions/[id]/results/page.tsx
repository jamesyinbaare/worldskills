import { redirect } from "next/navigation";

export default async function LegacyResultsRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/admin/results?competitionId=${encodeURIComponent(id)}`);
}
