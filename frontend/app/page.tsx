import Image from "next/image";
import Link from "next/link";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import { HomeOpenCompetitions } from "@/components/competitions/HomeOpenCompetitions";
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

export default function Home() {
  return (
    <>
      <section className="relative isolate flex min-h-[max(22rem,calc(68dvh-var(--site-header-height)))] overflow-hidden bg-brand-blue sm:min-h-[max(26rem,calc(72dvh-var(--site-header-height)))] lg:min-h-[max(30rem,calc(78dvh-var(--site-header-height)))] xl:min-h-[max(34rem,calc(82dvh-var(--site-header-height)))]">
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
    </>
  );
}

