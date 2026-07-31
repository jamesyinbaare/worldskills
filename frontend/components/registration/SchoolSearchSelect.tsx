"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Building2, Check, ChevronsUpDown, Loader2, X } from "lucide-react";
import {
  searchInstitutions,
  type InstitutionLookupOut,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type SchoolSelection = {
  institutionId: string;
  code: string;
  name: string;
} | null;

type SchoolSearchSelectProps = {
  value: SchoolSelection;
  onChange: (school: SchoolSelection) => void;
  disabled?: boolean;
  error?: string | null;
  className?: string;
};

export function SchoolSearchSelect({
  value,
  onChange,
  disabled,
  error,
  className,
}: SchoolSearchSelectProps) {
  const listId = useId();
  const inputId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<InstitutionLookupOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [searched, setSearched] = useState(false);

  const clearSelection = useCallback(() => {
    onChange(null);
    setQuery("");
    setResults([]);
    setSearched(false);
    setOpen(false);
  }, [onChange]);

  useEffect(() => {
    if (!open) return;
    function onDocPointer(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocPointer);
    return () => document.removeEventListener("mousedown", onDocPointer);
  }, [open]);

  useEffect(() => {
    const q = query.trim();
    if (!open || q.length < 2) {
      setResults([]);
      setLoading(false);
      setSearched(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const rows = await searchInstitutions(q);
          if (!cancelled) {
            setResults(rows);
            setHighlight(0);
            setSearched(true);
          }
        } catch {
          if (!cancelled) {
            setResults([]);
            setSearched(true);
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, open]);

  function selectSchool(school: InstitutionLookupOut) {
    onChange({
      institutionId: school.institutionId,
      code: school.code,
      name: school.name,
    });
    setQuery("");
    setResults([]);
    setOpen(false);
    setSearched(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const pick = results[highlight];
      if (pick) selectSchool(pick);
    }
  }

  return (
    <div ref={rootRef} className={cn("relative space-y-2", className)}>
      {value ? (
        <div
          className="flex items-start gap-3 rounded-lg border border-brand-blue/20 bg-brand-blue/[0.04] px-3 py-3"
          data-testid="school-selected"
        >
          <Building2
            className="mt-0.5 size-5 shrink-0 text-brand-blue"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-foreground">{value.name}</p>
            {value.code ? (
              <p className="text-xs text-muted-foreground">
                Code <span className="font-mono">{value.code}</span>
              </p>
            ) : null}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-9 shrink-0 gap-1 px-2"
            disabled={disabled}
            onClick={clearSelection}
            data-testid="school-clear"
          >
            <X className="size-4" aria-hidden />
            Clear
          </Button>
        </div>
      ) : (
        <>
          <div className="relative">
            <Input
              id={inputId}
              role="combobox"
              aria-expanded={open}
              aria-controls={listId}
              aria-autocomplete="list"
              aria-invalid={Boolean(error)}
              className="min-h-11 pr-10"
              placeholder="Search by school name or code…"
              value={query}
              disabled={disabled}
              autoComplete="off"
              data-testid="school-search"
              onFocus={() => setOpen(true)}
              onChange={(e) => {
                setQuery(e.target.value);
                setOpen(true);
              }}
              onKeyDown={onKeyDown}
            />
            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-muted-foreground">
              {loading ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <ChevronsUpDown className="size-4" aria-hidden />
              )}
            </span>
          </div>

          {open ? (
            <div
              id={listId}
              role="listbox"
              className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-popover shadow-md"
              data-testid="school-search-results"
            >
              {query.trim().length < 2 ? (
                <p className="px-3 py-3 text-sm text-muted-foreground">
                  Type at least 2 characters to search.
                </p>
              ) : loading ? (
                <p className="px-3 py-3 text-sm text-muted-foreground">
                  Searching schools…
                </p>
              ) : results.length === 0 && searched ? (
                <p className="px-3 py-3 text-sm text-muted-foreground">
                  No schools match “{query.trim()}”.
                </p>
              ) : (
                <ul className="py-1">
                  {results.map((school, index) => {
                    const active = index === highlight;
                    return (
                      <li key={school.institutionId}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={active}
                          className={cn(
                            "flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm transition-colors",
                            active
                              ? "bg-brand-blue/10 text-foreground"
                              : "hover:bg-muted/80",
                          )}
                          onMouseEnter={() => setHighlight(index)}
                          onClick={() => selectSchool(school)}
                        >
                          <Check
                            className={cn(
                              "mt-0.5 size-4 shrink-0 text-brand-blue",
                              active ? "opacity-100" : "opacity-0",
                            )}
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block font-medium">{school.name}</span>
                            <span className="block text-xs text-muted-foreground">
                              {school.code}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
