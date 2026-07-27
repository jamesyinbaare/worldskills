import { redirect } from "next/navigation";

export default async function LegacyAppealsRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/admin/appeals?competitionId=${encodeURIComponent(id)}`);
}
