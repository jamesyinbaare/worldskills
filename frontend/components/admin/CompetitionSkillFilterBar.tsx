"use client";

import { SearchIcon } from "lucide-react";
import { useEffect, useState } from "react";
import {
  ApiError,
  CompetitionListItem,
  SkillOut,
  apiFetch,
  listSkills,
} from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL_SKILLS = "__all__";

export type CompetitionSkillFilterValue = {
  competitionId: string;
  skillId: string;
  q: string;
};

type Props = {
  value: CompetitionSkillFilterValue;
  onChange: (next: CompetitionSkillFilterValue) => void;
  searchPlaceholder?: string;
};

export function CompetitionSkillFilterBar({
  value,
  onChange,
  searchPlaceholder = "Search…",
}: Props) {
  const [competitions, setCompetitions] = useState<CompetitionListItem[]>([]);
  const [skills, setSkills] = useState<SkillOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [qDraft, setQDraft] = useState(value.q);

  useEffect(() => {
    setQDraft(value.q);
  }, [value.q]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await apiFetch<CompetitionListItem[]>("/competitions");
        if (!cancelled) {
          setCompetitions(list);
          setLoadError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : "Could not load competitions",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!value.competitionId) {
      setSkills([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const list = await listSkills(value.competitionId);
        if (!cancelled) setSkills(list);
      } catch {
        if (!cancelled) setSkills([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [value.competitionId]);

  function setCompetition(competitionId: string) {
    onChange({ competitionId, skillId: "", q: value.q });
  }

  function setSkill(raw: string) {
    onChange({
      ...value,
      skillId: raw === ALL_SKILLS ? "" : raw,
    });
  }

  function commitSearch() {
    onChange({ ...value, q: qDraft.trim() });
  }

  return (
    <div
      className="admin-panel sticky top-14 z-10 space-y-3 rounded-[1.25rem] bg-card p-4 shadow-sm ring-1 ring-foreground/5 sm:p-5"
      data-testid="competition-skill-filter-bar"
    >
      {loadError ? (
        <p className="text-sm text-destructive">{loadError}</p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-1.5">
          <Label htmlFor="run-competition">Competition</Label>
          <Select
            value={value.competitionId || undefined}
            onValueChange={setCompetition}
          >
            <SelectTrigger
              id="run-competition"
              className="min-h-10 w-full"
              data-testid="filter-competition"
            >
              <SelectValue placeholder="Select a competition" />
            </SelectTrigger>
            <SelectContent>
              {competitions.map((c) => (
                <SelectItem key={c.competitionId} value={c.competitionId}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="run-skill">Skill area</Label>
          <Select
            value={value.skillId || ALL_SKILLS}
            onValueChange={setSkill}
            disabled={!value.competitionId}
          >
            <SelectTrigger
              id="run-skill"
              className="min-h-10 w-full"
              data-testid="filter-skill"
            >
              <SelectValue placeholder="All skills" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_SKILLS}>All skills</SelectItem>
              {skills.map((s) => (
                <SelectItem key={s.skillId} value={s.skillId}>
                  {s.name}
                  {s.number ? ` (${s.number})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="run-search">Search</Label>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="run-search"
              className="min-h-10 pl-9"
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitSearch();
                }
              }}
              onBlur={commitSearch}
              placeholder={searchPlaceholder}
              disabled={!value.competitionId}
              data-testid="filter-search"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
