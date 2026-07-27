import { redirect } from "next/navigation";

export default async function LegacyScheduleRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/admin/schedule?competitionId=${encodeURIComponent(id)}`);
}
