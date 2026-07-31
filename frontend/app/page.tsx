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
      <section className="relative isolate min-h-[calc(100dvh-var(--site-header-height))] overflow-hidden bg-brand-blue">
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

        <div className="relative mx-auto flex min-h-[calc(100dvh-var(--site-header-height))] max-w-6xl flex-col justify-center gap-8 px-4 py-16 sm:px-6 sm:py-24 lg:py-28">
          <div
            className="animate-hero-fade flex max-w-xl items-center gap-4 sm:gap-5"
            aria-label="WorldSkills Ghana and CTVET"
          >
            <WorldSkillsLogo
              className="h-20 w-auto max-w-[16rem] shrink-0 object-contain object-left sm:h-24 sm:max-w-[20rem]"
              priority
            />
            <div
              className="h-16 w-px shrink-0 bg-white/45 sm:h-20"
              aria-hidden
            />
            <CrestLogo
              className="h-20 w-auto shrink-0 object-contain drop-shadow-md sm:h-24"
              priority
            />
          </div>

          <div className="animate-hero-slide max-w-xl space-y-5">
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
                <a href="#competitions">Explore what&apos;s open</a>
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
        className="border-t border-border bg-muted px-4 py-16 sm:px-6 sm:py-20"
      >
        <div className="mx-auto max-w-6xl">
          <h2 className="sr-only">How it works</h2>
          <ol className="grid gap-10 sm:grid-cols-3 sm:gap-0">
            {journeySteps.map((step, index) => (
              <li
                key={step.number}
                className={`animate-journey-step relative px-0 sm:px-8 ${
                  index > 0 ? "sm:border-l sm:border-brand-gold/50" : ""
                }`}
                style={{ animationDelay: `${0.15 * index}s` }}
              >
                <p
                  className="text-4xl font-bold tracking-tight text-primary/15 sm:text-5xl"
                  aria-hidden
                >
                  {step.number}
                </p>
                <h3 className="mt-3 text-lg font-bold tracking-tight text-primary">
                  {step.title}
                </h3>
                <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground sm:text-base">
                  {step.description}
                </p>
              </li>
            ))}
          </ol>
          <p className="mt-12 text-center">
            <a
              href="#competitions"
              className="text-sm font-semibold text-primary underline-offset-4 hover:underline"
            >
              Explore what&apos;s open
            </a>
          </p>
        </div>
      </section>
    </>
  );
}
