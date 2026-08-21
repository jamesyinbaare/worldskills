"use client";

import { useEffect, useId, useState } from "react";
import { ArrowUpRightIcon } from "lucide-react";
import {
  fetchPublicSponsorLogo,
  listPublicSponsors,
  type SponsorOut,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const logoCache = new Map<string, string>();

function SponsorLogo({
  sponsorId,
  hasLogo,
  name,
  className,
  monogramClassName,
}: {
  sponsorId: string;
  hasLogo: boolean;
  name: string;
  className?: string;
  monogramClassName?: string;
}) {
  const [src, setSrc] = useState<string | null>(
    () => logoCache.get(sponsorId) ?? null,
  );

  useEffect(() => {
    if (!hasLogo) {
      setSrc(null);
      return;
    }
    const cached = logoCache.get(sponsorId);
    if (cached) {
      setSrc(cached);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const { blob } = await fetchPublicSponsorLogo(sponsorId);
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        logoCache.set(sponsorId, objectUrl);
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setSrc(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sponsorId, hasLogo]);

  if (!hasLogo || !src) {
    return (
      <div
        className={cn(
          "flex size-14 items-center justify-center rounded-full bg-white/15 text-xl font-bold tracking-tight text-white/90 transition duration-300 group-hover:bg-brand-gold/25 group-hover:text-white sm:size-16",
          monogramClassName,
        )}
        aria-hidden
      >
        {name.slice(0, 1).toUpperCase()}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- blob: from public API
    <img
      src={src}
      alt=""
      width={180}
      height={72}
      className={cn(
        "max-h-12 w-auto max-w-40 object-contain opacity-95 transition duration-500 group-hover:scale-105 group-hover:opacity-100 group-focus-visible:scale-105 group-focus-visible:opacity-100 sm:max-h-14 sm:max-w-48",
        className,
      )}
    />
  );
}

function SponsorTile({
  sponsor,
  index,
  onOpenDetails,
}: {
  sponsor: SponsorOut;
  index: number;
  onOpenDetails: (sponsor: SponsorOut) => void;
}) {
  const hasDetails = Boolean(sponsor.description?.trim());
  const hasWebsite = Boolean(sponsor.website);

  const sharedClass =
    "group relative flex h-36 w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-[1.35rem] px-5 outline-none transition duration-500 focus-visible:ring-2 focus-visible:ring-brand-gold sm:h-40";

  const inner = (
    <>
      <span
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_70%_at_50%_0%,rgba(255,204,0,0.16),transparent_60%)] opacity-0 transition duration-500 group-hover:opacity-100 group-focus-visible:opacity-100"
        aria-hidden
      />
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-0.5 origin-left scale-x-0 bg-linear-to-r from-transparent via-brand-gold to-transparent transition duration-500 group-hover:scale-x-100 group-focus-visible:scale-x-100"
        aria-hidden
      />
      <span
        className="pointer-events-none absolute inset-x-8 bottom-0 h-px origin-center scale-x-0 bg-brand-gold/50 transition duration-500 delay-75 group-hover:scale-x-100 group-focus-visible:scale-x-100"
        aria-hidden
      />

      <div className="relative z-10 flex min-h-16 items-center justify-center">
        <SponsorLogo
          sponsorId={sponsor.sponsorId}
          hasLogo={sponsor.hasLogo}
          name={sponsor.name}
        />
      </div>

      <span className="relative z-10 max-w-48 truncate text-center text-[0.65rem] font-semibold tracking-[0.2em] text-white/75 uppercase transition duration-500 group-hover:text-brand-gold group-focus-visible:text-brand-gold sm:text-[0.7rem]">
        {sponsor.name}
      </span>
    </>
  );

  if (hasDetails) {
    return (
      <button
        type="button"
        className={sharedClass}
        style={{ animationDelay: `${0.08 + index * 0.07}s` }}
        onClick={() => onOpenDetails(sponsor)}
        aria-label={`About ${sponsor.name}`}
      >
        {inner}
      </button>
    );
  }

  if (hasWebsite) {
    return (
      <a
        href={sponsor.website!}
        target="_blank"
        rel="noopener noreferrer"
        className={sharedClass}
        style={{ animationDelay: `${0.08 + index * 0.07}s` }}
        aria-label={`${sponsor.name} (opens website)`}
      >
        {inner}
      </a>
    );
  }

  return (
    <div
      className={cn(sharedClass, "cursor-default")}
      style={{ animationDelay: `${0.08 + index * 0.07}s` }}
      aria-label={sponsor.name}
    >
      {inner}
    </div>
  );
}

export function HomeSponsors() {
  const titleId = useId();
  const [sponsors, setSponsors] = useState<SponsorOut[] | null>(null);
  const [selected, setSelected] = useState<SponsorOut | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const items = await listPublicSponsors();
        if (!cancelled) setSponsors(items);
      } catch {
        if (!cancelled) setSponsors([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!sponsors || sponsors.length === 0) {
    return null;
  }

  return (
    <section
      id="sponsors"
      aria-labelledby={titleId}
      className="relative scroll-mt-(--site-header-height) overflow-hidden border-t border-brand-blue/20 bg-brand-blue px-4 py-20 text-white sm:px-6 sm:py-24 lg:py-28"
    >
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_55%_at_50%_-10%,rgba(255,204,0,0.2),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_45%_40%_at_0%_100%,rgba(0,133,63,0.18),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_40%_35%_at_100%_70%,rgba(227,6,19,0.1),transparent_45%)]" />
        <div className="absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-brand-gold/60 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-transparent via-brand-gold/40 to-transparent" />
      </div>

      <div className="relative mx-auto max-w-6xl">
        <header className="animate-comp-fade mx-auto max-w-2xl space-y-5 text-center">
          <div className="flex items-center justify-center gap-3">
            <span
              className="h-px w-8 bg-linear-to-r from-transparent to-brand-gold/80 sm:w-12"
              aria-hidden
            />
            <p className="text-xs font-semibold tracking-[0.22em] text-brand-gold uppercase">
              Partners
            </p>
            <span
              className="h-px w-8 bg-linear-to-l from-transparent to-brand-gold/80 sm:w-12"
              aria-hidden
            />
          </div>
          <h2
            id={titleId}
            className="text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl"
          >
            Proudly supported by
          </h2>
          <p className="mx-auto max-w-md text-base leading-relaxed text-white/70 sm:text-lg">
            Organizations standing with WorldSkills Ghana.
          </p>
        </header>

        <ul
          className={cn(
            "animate-comp-fade mt-14 grid gap-4 sm:mt-16 sm:gap-5",
            sponsors.length === 1 && "mx-auto max-w-sm",
            sponsors.length === 2 && "mx-auto max-w-3xl grid-cols-2",
            sponsors.length === 3 && "grid-cols-1 sm:grid-cols-3",
            sponsors.length >= 4 && "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
          )}
        >
          {sponsors.map((sponsor, index) => (
            <li
              key={sponsor.sponsorId}
              className="animate-comp-fade rounded-[1.35rem] bg-white/12 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] ring-1 ring-white/20 backdrop-blur-md transition duration-500 hover:-translate-y-1 hover:bg-white/16 hover:ring-brand-gold/40 hover:shadow-[0_24px_48px_-28px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,204,0,0.25)]"
            >
              <SponsorTile
                sponsor={sponsor}
                index={index}
                onOpenDetails={setSelected}
              />
            </li>
          ))}
        </ul>
      </div>

      <Dialog
        open={selected != null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent className="gap-0 overflow-hidden border-brand-blue/10 p-0 sm:max-w-md">
          {selected ? (
            <>
              <div className="relative flex items-center justify-center overflow-hidden bg-brand-blue px-6 py-10">
                <div
                  className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_50%_0%,rgba(255,204,0,0.22),transparent_60%)]"
                  aria-hidden
                />
                <div className="relative rounded-2xl bg-white/95 px-8 py-6 shadow-[0_20px_40px_-24px_rgba(0,0,0,0.5)]">
                  <SponsorLogo
                    sponsorId={selected.sponsorId}
                    hasLogo={selected.hasLogo}
                    name={selected.name}
                    className="max-h-16 max-w-52 opacity-100"
                    monogramClassName="bg-brand-blue/8 text-brand-blue"
                  />
                </div>
              </div>
              <DialogHeader className="space-y-3 px-6 pt-6 pb-2 text-left">
                <DialogTitle className="text-xl font-bold tracking-tight text-primary">
                  {selected.name}
                </DialogTitle>
                {selected.description ? (
                  <DialogDescription className="text-sm leading-relaxed text-muted-foreground">
                    {selected.description}
                  </DialogDescription>
                ) : null}
                {(selected.skillAreas?.length ?? 0) > 0 ? (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-[0.65rem] font-semibold tracking-[0.16em] text-brand-blue/70 uppercase">
                      Supports
                    </p>
                    <ul className="flex flex-wrap gap-1.5">
                      {selected.skillAreas!.map((area) => (
                        <li
                          key={area.catalogSkillId}
                          className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground"
                        >
                          {area.number
                            ? `${area.name} (${area.number})`
                            : area.name}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </DialogHeader>
              <div className="flex flex-wrap gap-2 px-6 pt-3 pb-6">
                {selected.website ? (
                  <Button asChild variant="accent" className="min-h-10 gap-1.5">
                    <a
                      href={selected.website}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Visit website
                      <ArrowUpRightIcon className="size-4" aria-hidden />
                    </a>
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-10"
                  onClick={() => setSelected(null)}
                >
                  Close
                </Button>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}
