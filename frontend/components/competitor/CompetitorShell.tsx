"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ClipboardListIcon,
  DatabaseIcon,
  FileWarningIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  ScaleIcon,
  ShieldCheckIcon,
  TrophyIcon,
} from "lucide-react";
import { CrestLogo } from "@/components/brand/LogoMark";
import { useAuth } from "@/components/auth/AuthProvider";
import type { MyRegistrationOut } from "@/lib/api";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function navActive(pathname: string, href: string, exact?: boolean): boolean {
  const pathOnly = href.split("?")[0];
  if (exact) return pathname === pathOnly;
  return pathname === pathOnly || pathname.startsWith(`${pathOnly}/`);
}

type CompetitorShellProps = {
  children: React.ReactNode;
  registrations: MyRegistrationOut[];
};

export function CompetitorShell({
  children,
  registrations,
}: CompetitorShellProps) {
  const pathname = usePathname();
  const { me, logout } = useAuth();

  const primaryCompetitorId = registrations[0]?.competitorId;

  return (
    <div className="competitor-shell min-h-svh bg-[var(--admin-canvas)]">
      <SidebarProvider
        style={
          {
            "--sidebar-width": "17rem",
            "--sidebar-width-icon": "5rem",
          } as React.CSSProperties
        }
      >
        <Sidebar collapsible="icon" variant="floating">
          <SidebarHeader className="gap-3 border-b border-sidebar-border/70 p-3 group-data-[collapsible=icon]:px-2 group-data-[collapsible=icon]:py-3">
            <div className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
              <CrestLogo className="h-10 w-auto shrink-0 object-contain group-data-[collapsible=icon]:h-9" />
              <div className="min-w-0 group-data-[collapsible=icon]:hidden">
                <p className="truncate text-sm font-bold tracking-tight text-sidebar-foreground">
                  WorldSkills Ghana
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  Competitor portal
                </p>
              </div>
            </div>
          </SidebarHeader>

          <SidebarContent className="px-2 py-4 group-data-[collapsible=icon]:px-1.5">
            <SidebarGroup className="px-1 group-data-[collapsible=icon]:px-0">
              <SidebarGroupLabel className="mb-2 px-3 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Menu
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
                  <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                    <SidebarMenuButton
                      asChild
                      isActive={navActive(pathname, "/competitor", true)}
                      size="lg"
                      tooltip="Overview"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/competitor", true) &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/competitor"
                        aria-current={
                          navActive(pathname, "/competitor", true)
                            ? "page"
                            : undefined
                        }
                        data-testid="competitor-nav-overview"
                      >
                        <LayoutDashboardIcon />
                        <span>Overview</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>

            <SidebarGroup className="px-1 group-data-[collapsible=icon]:px-0">
              <SidebarGroupLabel className="mb-2 px-3 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                My competitions
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
                  {registrations.map((reg) => {
                    const base = `/competitor/competitions/${reg.competitionId}`;
                    const active = navActive(pathname, base);
                    return (
                      <SidebarMenuItem
                        key={reg.competitorId}
                        className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center"
                      >
                        <SidebarMenuButton
                          asChild
                          isActive={active}
                          size="lg"
                          tooltip={reg.competitionName}
                          className={cn(
                            "rounded-2xl px-3 font-medium",
                            !active && "text-sidebar-foreground/65",
                          )}
                        >
                          <Link
                            href={base}
                            aria-current={active ? "page" : undefined}
                            data-testid={`competitor-nav-competition-${reg.competitionId}`}
                          >
                            <TrophyIcon />
                            <span className="truncate">{reg.competitionName}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>

            {registrations.length === 1 ? (
              <SidebarGroup className="px-1 group-data-[collapsible=icon]:px-0">
                <SidebarGroupLabel className="mb-2 px-3 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  This competition
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
                    {(
                      [
                        {
                          href: `/competitor/competitions/${registrations[0].competitionId}`,
                          label: "Stages",
                          icon: ClipboardListIcon,
                          exact: true,
                          testId: "competitor-nav-stages",
                        },
                        {
                          href: `/competitor/competitions/${registrations[0].competitionId}/results`,
                          label: "Results",
                          icon: ScaleIcon,
                          testId: "competitor-nav-results",
                        },
                        {
                          href: `/competitor/appeals/new?competitionId=${registrations[0].competitionId}`,
                          label: "Appeal",
                          icon: FileWarningIcon,
                          testId: "competitor-nav-appeal",
                        },
                      ] as const
                    ).map((item) => {
                      const active = navActive(
                        pathname,
                        item.href,
                        "exact" in item ? item.exact : false,
                      );
                      const Icon = item.icon;
                      return (
                        <SidebarMenuItem
                          key={item.href}
                          className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center"
                        >
                          <SidebarMenuButton
                            asChild
                            isActive={active}
                            size="lg"
                            tooltip={item.label}
                            className={cn(
                              "rounded-2xl px-3 font-medium",
                              !active && "text-sidebar-foreground/65",
                            )}
                          >
                            <Link
                              href={item.href}
                              aria-current={active ? "page" : undefined}
                              data-testid={item.testId}
                            >
                              <Icon />
                              <span>{item.label}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ) : null}

            <SidebarGroup className="px-1 group-data-[collapsible=icon]:px-0">
              <SidebarGroupLabel className="mb-2 px-3 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Account
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
                  {primaryCompetitorId ? (
                    <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                      <SidebarMenuButton
                        asChild
                        isActive={navActive(
                          pathname,
                          `/competitor/competitors/${primaryCompetitorId}/consent`,
                        )}
                        size="lg"
                        tooltip="Guardian consent"
                        className={cn(
                          "rounded-2xl px-3 font-medium",
                          !navActive(
                            pathname,
                            `/competitor/competitors/${primaryCompetitorId}/consent`,
                          ) && "text-sidebar-foreground/65",
                        )}
                      >
                        <Link
                          href={`/competitor/competitors/${primaryCompetitorId}/consent`}
                          data-testid="competitor-nav-consent"
                        >
                          <ShieldCheckIcon />
                          <span>Guardian consent</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ) : null}
                  <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                    <SidebarMenuButton
                      asChild
                      isActive={navActive(pathname, "/competitor/dsar")}
                      size="lg"
                      tooltip="Data requests"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/competitor/dsar") &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/competitor/dsar"
                        data-testid="competitor-nav-dsar"
                      >
                        <DatabaseIcon />
                        <span>Data requests</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>

          <SidebarFooter className="gap-3 border-t border-sidebar-border/70 p-3 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:px-1.5">
            {me ? (
              <div className="rounded-2xl bg-muted/80 px-3 py-3 group-data-[collapsible=icon]:hidden">
                <p className="truncate text-sm font-semibold text-sidebar-foreground">
                  {me.full_name ?? me.email}
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  Competitor
                </p>
              </div>
            ) : null}
            <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
              <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                <SidebarMenuButton
                  size="lg"
                  tooltip="Sign out"
                  className="rounded-2xl px-3 text-sidebar-foreground/70 hover:text-destructive"
                  onClick={logout}
                  data-testid="competitor-nav-sign-out"
                >
                  <LogOutIcon />
                  <span>Sign out</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarFooter>
          <SidebarRail />
        </Sidebar>

        <SidebarInset className="bg-transparent">
          <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 px-3 md:px-5">
            <SidebarTrigger className="min-h-10 min-w-10 rounded-2xl border border-border/70 bg-card shadow-sm" />
            <div className="min-w-0 flex-1" />
            <Button
              variant="outline"
              className="hidden min-h-10 rounded-2xl border-border/70 bg-card shadow-sm sm:inline-flex"
              asChild
            >
              <Link href="/">Public site</Link>
            </Button>
          </header>
          <div className="flex-1 px-3 pb-6 sm:px-5 sm:pb-8 lg:px-6">
            {children}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}
