import Image from "next/image";
import Link from "next/link";
import { MessageCircle, Phone } from "lucide-react";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import { HomeOpenCompetitions } from "@/components/competitions/HomeOpenCompetitions";
import { HomeLiveStats } from "@/components/home/HomeLiveStats";
import { Button } from "@/components/ui/button";

const journeySteps = [
  {
    number: "01",
    title: "Register",
    description: "Create a competitor account and enter your skill area",
  },
  {
    number: "02",
    title: "Compete",
    description: "Skills assessed under national standards",
  },
  {
    number: "03",
    title: "Excel",
    description: "Shortlisting and results with fairness",
  },
] as const;

const contactTeam = [
  { name: "Eunice", e164: "233596874163", display: "+233 59 687 4163" },
  { name: "Mayer", e164: "233263145572", display: "+233 26 314 5572" },
  { name: "Bestina", e164: "233599252548", display: "+233 59 925 2548" },
  { name: "Beatrice", e164: "233598105441", display: "+233 59 810 5441" },
  { name: "Sylvester", e164: "233204681951", display: "+233 20 468 1951" },
  { name: "Frank", e164: "233509655330", display: "+233 50 965 5330" },
] as const;

export default function Home() {
  return (
    <>
      <section className="relative isolate flex min-h-[max(22rem,calc(68dvh-var(--site-header-height)))] flex-col overflow-hidden bg-brand-blue sm:min-h-[max(26rem,calc(72dvh-var(--site-header-height)))] lg:min-h-[max(30rem,calc(78dvh-var(--site-header-height)))] xl:min-h-[max(34rem,calc(82dvh-var(--site-header-height)))]">
        <div className="absolute inset-0" aria-hidden>
          <Image
            src="/auto2.jpg"
            alt=""
            fill
            priority
            sizes="100vw"
            className="animate-hero-image object-cover object-[center_30%] sm:object-center"
          />
          <div className="hero-ceremonial-wash absolute inset-0" />
        </div>

        <div className="relative mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center gap-6 px-4 py-14 sm:gap-8 sm:px-6 sm:py-16 lg:py-20">
          <div
            className="animate-hero-fade flex max-w-xl items-center gap-4 sm:gap-5"
            aria-label="WorldSkills Ghana and CTVET"
          >
            <WorldSkillsLogo
              className="h-16 w-auto max-w-[14rem] shrink-0 object-contain object-left sm:h-20 sm:max-w-[18rem] lg:h-24 lg:max-w-[20rem]"
              priority
            />
            <div
              className="h-14 w-px shrink-0 bg-white/45 sm:h-16 lg:h-20"
              aria-hidden
            />
            <CrestLogo
              className="h-16 w-auto shrink-0 object-contain drop-shadow-md sm:h-20 lg:h-24"
              priority
            />
          </div>

          <div className="animate-hero-slide max-w-xl space-y-4 sm:space-y-5">
            <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">
              Compete. Excel.{" "}
              <span className="text-brand-gold">Represent Ghana.</span>
            </h1>
            <p className="max-w-md text-base leading-relaxed text-white/80 sm:text-lg">
              The official website of WorldSkills Ghana — under CTVET
              governance. Register to compete.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Button size="lg" variant="accent" className="min-h-11" asChild>
                <a href="#competitions">Browse open skills</a>
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="min-h-11 border-white/40 bg-transparent text-white hover:bg-white/10 hover:text-white"
                asChild
              >
                <Link href="/login">Login</Link>
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="min-h-11 border-white/40 bg-transparent text-white hover:bg-white/10 hover:text-white"
                asChild
              >
                <Link href="/signup">Register</Link>
              </Button>
            </div>
          </div>
        </div>

        <HomeLiveStats />
      </section>

      <HomeOpenCompetitions />

      <section
        id="journey"
        className="relative overflow-hidden border-t border-border bg-brand-blue px-4 py-20 text-white sm:px-6 sm:py-24 lg:py-28"
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-90"
          aria-hidden
        >
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_55%_at_12%_0%,rgba(255,204,0,0.18),transparent_58%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_55%_45%_at_100%_80%,rgba(0,133,63,0.22),transparent_55%)]" />
          <div className="absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-transparent via-brand-gold/50 to-transparent" />
        </div>

        <div className="relative mx-auto max-w-6xl">
          <header className="animate-journey-step mx-auto max-w-2xl space-y-4 text-center">
            <p className="text-xs font-semibold tracking-[0.18em] text-brand-gold uppercase">
              The path
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">
              How it works
            </h2>
            <p className="mx-auto max-w-lg text-base leading-relaxed text-white/75 sm:text-lg">
              Three clear steps from signup to national recognition.
            </p>
          </header>

          <ol className="relative mt-14 grid gap-0 sm:mt-16 sm:grid-cols-3 sm:gap-0 lg:mt-20">
            {/* Desktop connector path */}
            <div
              className="pointer-events-none absolute top-7 right-[16.666%] left-[16.666%] hidden h-px bg-linear-to-r from-brand-gold/20 via-brand-gold/70 to-brand-gold/20 sm:block"
              aria-hidden
            />

            {journeySteps.map((step, index) => (
              <li
                key={step.number}
                className="animate-journey-step relative flex gap-5 pb-12 last:pb-0 sm:flex-col sm:items-center sm:gap-0 sm:px-6 sm:pb-0 sm:text-center lg:px-10"
                style={{ animationDelay: `${0.12 + 0.14 * index}s` }}
              >
                {/* Mobile vertical connector */}
                {index < journeySteps.length - 1 ? (
                  <span
                    className="absolute top-12 bottom-0 left-5 w-px bg-linear-to-b from-brand-gold/70 to-brand-gold/15 sm:hidden"
                    aria-hidden
                  />
                ) : null}

                <div className="relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-gold font-bold tracking-tight text-brand-blue shadow-[0_0_0_6px_rgba(0,55,100,0.35)] sm:mx-auto sm:size-14 sm:text-sm sm:shadow-[0_0_0_8px_rgba(0,55,100,0.4)]">
                  <span className="sr-only">Step </span>
                  {step.number}
                </div>

                <div className="min-w-0 flex-1 space-y-2 pt-1 sm:mt-8 sm:space-y-3 sm:pt-0">
                  <h3 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
                    {step.title}
                  </h3>
                  <p className="max-w-xs text-sm leading-relaxed text-white/70 sm:mx-auto sm:text-base">
                    {step.description}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          <div
            className="animate-journey-step mt-12 flex justify-center sm:mt-16"
            style={{ animationDelay: "0.55s" }}
          >
            <Button
              size="lg"
              variant="accent"
              className="min-h-12 rounded-2xl px-8"
              asChild
            >
              <a href="#competitions">Browse open skills</a>
            </Button>
          </div>
        </div>
      </section>

      <section
        id="support"
        className="relative scroll-mt-[var(--site-header-height)] overflow-hidden border-t border-border bg-[linear-gradient(180deg,#f8fafb_0%,#eef3f7_100%)] px-4 py-20 sm:px-6 sm:py-24 lg:py-28"
      >
        <div className="pointer-events-none absolute inset-0" aria-hidden>
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_55%_45%_at_100%_0%,rgba(0,55,100,0.06),transparent_55%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_45%_40%_at_0%_100%,rgba(0,133,63,0.07),transparent_50%)]" />
        </div>

        <div className="relative mx-auto max-w-6xl">
          <header className="animate-journey-step mx-auto max-w-2xl space-y-4 text-center">
            <p className="text-xs font-semibold tracking-[0.18em] text-brand-blue/70 uppercase">
              Support
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-brand-blue sm:text-4xl lg:text-5xl">
              For more information
            </h2>
            <p className="mx-auto max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg">
              Reach the WorldSkills Ghana team directly by call or WhatsApp.
            </p>
          </header>

          <div
            className="animate-journey-step mx-auto mt-10 h-px max-w-md bg-linear-to-r from-transparent via-brand-blue/25 to-transparent sm:mt-12"
            style={{ animationDelay: "0.1s" }}
            aria-hidden
          />

          <ul className="mx-auto mt-10 max-w-3xl divide-y divide-brand-blue/10 rounded-2xl border border-brand-blue/10 bg-white/90 px-4 sm:mt-12 sm:px-6">
            {contactTeam.map((person, index) => (
              <li
                key={person.e164}
                className="animate-journey-step flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:py-6"
                style={{ animationDelay: `${0.12 + 0.07 * index}s` }}
              >
                <div className="flex min-w-0 items-center gap-4">
                  <span
                    className="flex size-12 shrink-0 items-center justify-center rounded-full bg-brand-blue/8 text-base font-bold tracking-tight text-brand-blue ring-1 ring-brand-blue/15"
                    aria-hidden
                  >
                    {person.name.slice(0, 1)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-lg font-bold tracking-tight text-brand-blue sm:text-xl">
                      {person.name}
                    </p>
                    <a
                      href={`tel:+${person.e164}`}
                      className="mt-0.5 inline-block font-mono text-sm tracking-wide text-muted-foreground transition-colors hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2"
                    >
                      {person.display}
                    </a>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 sm:flex sm:shrink-0 sm:gap-2.5">
                  <a
                    href={`tel:+${person.e164}`}
                    aria-label={`Call ${person.name}`}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-brand-blue/20 bg-white px-4 text-sm font-semibold text-brand-blue transition-colors hover:border-brand-blue/40 hover:bg-brand-blue/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue focus-visible:ring-offset-2"
                  >
                    <Phone className="size-4 opacity-90" aria-hidden />
                    Call
                  </a>
                  <a
                    href={`https://wa.me/${person.e164}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`WhatsApp ${person.name}`}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand-green px-4 text-sm font-semibold text-white transition-colors hover:bg-[#06964a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-green focus-visible:ring-offset-2"
                  >
                    <MessageCircle className="size-4 opacity-95" aria-hidden />
                    WhatsApp
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
