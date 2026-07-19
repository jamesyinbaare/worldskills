"use client";

import Link from "next/link";
import { MenuIcon } from "lucide-react";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/admin/cycles", label: "Cycles" },
  { href: "/login", label: "Login" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-3"
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
            <Button key={item.label} variant="ghost" size="sm" asChild>
              <Link href={item.href}>{item.label}</Link>
            </Button>
          ))}
          <Button variant="accent" size="default" className="ml-2" asChild>
            <Link href="/login">Enter portal</Link>
          </Button>
        </nav>

        <Sheet>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open menu"
            >
              <MenuIcon />
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="w-[min(100%,20rem)]">
            <SheetHeader>
              <SheetTitle>Menu</SheetTitle>
            </SheetHeader>
            <nav className="mt-4 flex flex-col gap-1" aria-label="Mobile">
              {navItems.map((item) => (
                <SheetClose key={item.label} asChild>
                  <Button variant="ghost" className="justify-start" asChild>
                    <Link href={item.href}>{item.label}</Link>
                  </Button>
                </SheetClose>
              ))}
              <SheetClose asChild>
                <Button variant="accent" className="mt-2" asChild>
                  <Link href="/login">Enter portal</Link>
                </Button>
              </SheetClose>
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}
