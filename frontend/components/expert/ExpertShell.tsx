"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ClipboardListIcon,
  LayoutDashboardIcon,
  LogOutIcon,
} from "lucide-react";
import { CrestLogo } from "@/components/brand/LogoMark";
import { useAuth } from "@/components/auth/AuthProvider";
import type { MyAssignmentOut } from "@/lib/api";
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

type CompetitionNav = {
  competitionId: string;
  competitionName: string;
};

function distinctCompetitions(assignments: MyAssignmentOut[]): CompetitionNav[] {
  const seen = new Map<string, CompetitionNav>();
  for (const a of assignments) {
    if (!seen.has(a.competitionId)) {
      seen.set(a.competitionId, {
        competitionId: a.competitionId,
        competitionName: a.competitionName,
      });
    }
  }
  return Array.from(seen.values());
}

type ExpertShellProps = {
  children: React.ReactNode;
  assignments: MyAssignmentOut[];
};

export function ExpertShell({ children, assignments }: ExpertShellProps) {
  const pathname = usePathname();
  const { me, logout } = useAuth();
  const competitions = distinctCompetitions(assignments);

  return (
    <div className="expert-shell min-h-svh bg-[var(--admin-canvas)]">
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
                  Assessor portal
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
                      isActive={navActive(pathname, "/expert", true)}
                      size="lg"
                      tooltip="Overview"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/expert", true) &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/expert"
                        aria-current={
                          navActive(pathname, "/expert", true)
                            ? "page"
                            : undefined
                        }
                        data-testid="expert-nav-overview"
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
                  {competitions.map((comp) => {
                    const href = `/expert/competitions/${comp.competitionId}/queue`;
                    const active = navActive(pathname, href);
                    return (
                      <SidebarMenuItem
                        key={comp.competitionId}
                        className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center"
                      >
                        <SidebarMenuButton
                          asChild
                          isActive={active}
                          size="lg"
                          tooltip={comp.competitionName}
                          className={cn(
                            "rounded-2xl px-3 font-medium",
                            !active && "text-sidebar-foreground/65",
                          )}
                        >
                          <Link
                            href={href}
                            aria-current={active ? "page" : undefined}
                            data-testid={`expert-nav-competition-${comp.competitionId}`}
                          >
                            <ClipboardListIcon />
                            <span className="truncate">
                              {comp.competitionName}
                            </span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
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
                  {me.role === "CHIEF_EXPERT" ? "Chief Expert" : "Expert"}
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
                  data-testid="expert-nav-sign-out"
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
