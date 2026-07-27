"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import {
  CompetitionSkillFilterBar,
  type CompetitionSkillFilterValue,
} from "@/components/admin/CompetitionSkillFilterBar";

export function useCompetitionSkillQuery(): {
  filters: CompetitionSkillFilterValue;
  setFilters: (next: CompetitionSkillFilterValue) => void;
} {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters = useMemo<CompetitionSkillFilterValue>(
    () => ({
      competitionId: searchParams.get("competitionId") ?? "",
      skillId: searchParams.get("skillId") ?? "",
      q: searchParams.get("q") ?? "",
    }),
    [searchParams],
  );

  const setFilters = useCallback(
    (next: CompetitionSkillFilterValue) => {
      const params = new URLSearchParams();
      if (next.competitionId) params.set("competitionId", next.competitionId);
      if (next.skillId) params.set("skillId", next.skillId);
      if (next.q) params.set("q", next.q);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  return { filters, setFilters };
}

export function RunCompetitionFilterBar({
  searchPlaceholder,
}: {
  searchPlaceholder?: string;
}) {
  const { filters, setFilters } = useCompetitionSkillQuery();
  return (
    <CompetitionSkillFilterBar
      value={filters}
      onChange={setFilters}
      searchPlaceholder={searchPlaceholder}
    />
  );
}
