import { redirect } from "next/navigation";

type PageProps = {
  params: Promise<{ competitionId: string }>;
  searchParams: Promise<{ stageId?: string }>;
};

/** Legacy path — appeals are lodged from /competitor/appeals/new with a competition picker. */
export default async function LegacyLodgeAppealRedirect({
  params,
  searchParams,
}: PageProps) {
  const { competitionId } = await params;
  const { stageId } = await searchParams;
  const qs = new URLSearchParams({ competitionId });
  if (stageId) qs.set("stageId", stageId);
  redirect(`/competitor/appeals/new?${qs.toString()}`);
}
