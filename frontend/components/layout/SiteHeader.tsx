"use client";

import Link from "next/link";
import { useState } from "react";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";

const navItems = [
  { href: "/", label: "Home" },
  { href: "#skills", label: "Skills" },
  { href: "#login", label: "Login" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-3 min-w-0"
          aria-label="WorldSkills Ghana home"
        >
          <CrestLogo className="h-10 w-auto shrink-0 object-contain sm:h-12" priority />
          <WorldSkillsLogo className="hidden h-9 w-auto max-w-[9.5rem] object-contain object-left sm:block md:max-w-[11rem]" />
          <span className="truncate text-sm font-bold tracking-tight text-foreground sm:hidden">
            WorldSkills Ghana
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
          {navItems.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
          <Link href="#login" className="btn-accent ml-2">
            Enter portal
          </Link>
        </nav>

        <button
          type="button"
          className="inline-flex items-center justify-center rounded-md p-2 text-foreground md:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="sr-only">Menu</span>
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden
          >
            {open ? (
              <path d="M6 6l12 12M18 6L6 18" />
            ) : (
              <path d="M4 7h16M4 12h16M4 17h16" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <nav
          id="mobile-nav"
          className="border-t border-border bg-background px-4 py-3 md:hidden"
          aria-label="Mobile"
        >
          <ul className="flex flex-col gap-1">
            {navItems.map((item) => (
              <li key={item.label}>
                <Link
                  href={item.href}
                  className="block rounded-md px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </Link>
              </li>
            ))}
            <li className="pt-2">
              <Link
                href="#login"
                className="btn-accent w-full"
                onClick={() => setOpen(false)}
              >
                Enter portal
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}
