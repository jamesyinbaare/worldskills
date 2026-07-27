"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MenuIcon } from "lucide-react";
import { CrestLogo, WorldSkillsLogo } from "@/components/brand/LogoMark";
import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  homeForRole,
  isAdminRole,
  isCompetitorRole,
  isExpertRole,
  isInstitutionRole,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string };

function portalLabel(role: string): string {
  if (isAdminRole(role)) return "Admin";
  if (isInstitutionRole(role)) return "School portal";
  if (isCompetitorRole(role)) return "My portal";
  if (isExpertRole(role)) return "Assessor";
  return "Portal";
}

export function SiteHeader() {
  const pathname = usePathname();
  const { status, me, logout } = useAuth();
  const signedIn = status === "authenticated" && me;

  const navItems: NavItem[] = [
    { href: "/", label: "Home" },
    { href: "/competitions", label: "Competitions" },
  ];

  const portalHref = signedIn ? homeForRole(me.role) : null;
  const portalText = signedIn ? portalLabel(me.role) : null;

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border/80 bg-background/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:gap-4 sm:px-6">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5 sm:gap-3"
          aria-label="WorldSkills Ghana home"
        >
          <CrestLogo className="h-10 w-auto shrink-0 object-contain sm:h-12" priority />
          <WorldSkillsLogo className="hidden h-9 w-auto max-w-[9.5rem] object-contain object-left sm:block md:max-w-[11rem]" />
          <span className="truncate text-sm font-bold tracking-tight text-foreground sm:hidden">
            WorldSkills Ghana
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
          {navItems.map((item) => {
            const active = isActive(item.href);
            return (
              <Button
                key={item.href}
                variant="ghost"
                size="sm"
                className={cn(
                  active &&
                    "bg-primary/10 font-semibold text-primary hover:bg-primary/15 hover:text-primary",
                )}
                asChild
              >
                <Link href={item.href} aria-current={active ? "page" : undefined}>
                  {item.label}
                </Link>
              </Button>
            );
          })}
          {signedIn && portalHref && portalText ? (
            <div className="ml-2 flex items-center gap-2">
              <Button variant="accent" size="default" asChild>
                <Link href={portalHref}>{portalText}</Link>
              </Button>
              <Button variant="ghost" size="default" onClick={logout}>
                Sign out
              </Button>
            </div>
          ) : (
            <div className="ml-2 flex items-center gap-1.5">
              <Button variant="outline" size="default" asChild>
                <Link href="/login">Login</Link>
              </Button>
              <Button variant="accent" size="default" asChild>
                <Link href="/signup">Register</Link>
              </Button>
            </div>
          )}
        </nav>

        <Sheet>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="min-h-11 min-w-11 md:hidden"
              aria-label="Open menu"
            >
              <MenuIcon />
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="w-[min(100%,20rem)] px-4">
            <SheetHeader className="text-left">
              <SheetTitle>Menu</SheetTitle>
            </SheetHeader>
            <nav className="mt-4 flex flex-col gap-1" aria-label="Mobile">
              {navItems.map((item) => {
                const active = isActive(item.href);
                return (
                  <SheetClose key={item.href} asChild>
                    <Button
                      variant="ghost"
                      className={cn(
                        "min-h-11 justify-start px-3",
                        active && "bg-primary/10 font-semibold text-primary",
                      )}
                      asChild
                    >
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                      >
                        {item.label}
                      </Link>
                    </Button>
                  </SheetClose>
                );
              })}
              {signedIn && portalHref && portalText ? (
                <div className="mt-4 space-y-2">
                  <SheetClose asChild>
                    <Button variant="accent" className="min-h-11 w-full" asChild>
                      <Link href={portalHref}>{portalText}</Link>
                    </Button>
                  </SheetClose>
                  <Button
                    variant="outline"
                    className="min-h-11 w-full"
                    onClick={logout}
                  >
                    Sign out
                  </Button>
                </div>
              ) : (
                <div className="mt-4 flex flex-col gap-2">
                  <SheetClose asChild>
                    <Button variant="outline" className="min-h-11 w-full" asChild>
                      <Link href="/login">Login</Link>
                    </Button>
                  </SheetClose>
                  <SheetClose asChild>
                    <Button variant="accent" className="min-h-11 w-full" asChild>
                      <Link href="/signup">Register</Link>
                    </Button>
                  </SheetClose>
                </div>
              )}
            </nav>
          </SheetContent>
        </Sheet>
      </div>
      <div
        className="h-0.5 bg-linear-to-r from-brand-blue via-brand-gold to-brand-red"
        aria-hidden
      />
    </header>
  );
}
