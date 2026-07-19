import Link from "next/link";
import { WorldSkillsLogo } from "@/components/brand/LogoMark";

export default function Home() {
  return (
    <>
      <section className="relative isolate min-h-[calc(100dvh-4.5rem)] overflow-hidden bg-brand-atmosphere">
        {/* WorldSkills-inspired ribbons */}
        <div
          className="pointer-events-none absolute inset-0 overflow-hidden"
          aria-hidden
        >
          <div className="animate-ribbon absolute -left-8 top-[18%] h-16 w-[42%] rounded-full bg-brand-red/40 blur-[1px]" />
          <div className="animate-ribbon absolute left-[8%] top-[28%] h-20 w-[48%] rounded-full bg-brand-blue/35 [animation-delay:0.6s]" />
          <div className="animate-ribbon absolute left-[18%] top-[38%] h-14 w-[40%] rounded-full bg-brand-gold/50 [animation-delay:1.2s]" />
          <div className="animate-ribbon absolute left-[28%] top-[46%] h-12 w-[36%] rounded-full bg-brand-green/45 [animation-delay:1.8s]" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-background/40" />
        </div>

        <div className="relative mx-auto flex max-w-6xl flex-col justify-center gap-8 px-4 py-16 sm:px-6 sm:py-24 lg:min-h-[calc(100dvh-4.5rem)] lg:py-28">
          <div className="animate-hero-fade max-w-xl">
            <WorldSkillsLogo
              className="h-auto w-full max-w-[17rem] object-contain object-left sm:max-w-[22rem]"
              priority
            />
          </div>

          <div className="animate-hero-slide max-w-xl space-y-5">
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl lg:text-5xl">
              Compete. Excel.{" "}
              <span className="text-primary">Represent Ghana.</span>
            </h1>
            <p className="max-w-md text-base text-muted-foreground sm:text-lg">
              The official Skills Competition Management System for WorldSkills
              Ghana — registration through results, under CTVET governance.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Link href="#login" className="btn-primary">
                Enter competition portal
              </Link>
              <Link href="#about" className="btn-secondary">
                Learn more
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section
        id="about"
        className="border-t border-border bg-muted px-4 py-16 sm:px-6 sm:py-20"
      >
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-2xl font-bold tracking-tight text-primary sm:text-3xl">
            Competition management for Ghana&apos;s skills excellence
          </h2>
          <p className="mt-4 text-base text-muted-foreground sm:text-lg">
            From cycle configuration and nominations to assessment, shortlisting,
            and embargoed results — one platform built for fairness, auditability,
            and national standards.
          </p>
        </div>
      </section>

      <div id="skills" className="sr-only" aria-hidden />
      <div id="login" className="sr-only" aria-hidden />
    </>
  );
}
