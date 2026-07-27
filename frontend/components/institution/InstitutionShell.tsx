"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboardIcon,
  LogOutIcon,
  TrophyIcon,
  UserPlusIcon,
} from "lucide-react";
import { CrestLogo } from "@/components/brand/LogoMark";
import { useAuth } from "@/components/auth/AuthProvider";
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
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

type InstitutionShellProps = {
  children: React.ReactNode;
};

export function InstitutionShell({
  children,
}: InstitutionShellProps) {
  const pathname = usePathname();
  const { me, logout } = useAuth();

  return (
    <div className="institution-shell min-h-svh bg-(--admin-canvas)">
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
                  Institution portal
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
                      isActive={navActive(pathname, "/institution", true)}
                      size="lg"
                      tooltip="Overview"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/institution", true) &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/institution"
                        aria-current={
                          navActive(pathname, "/institution", true)
                            ? "page"
                            : undefined
                        }
                        data-testid="institution-nav-overview"
                      >
                        <LayoutDashboardIcon />
                        <span>Overview</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                    <SidebarMenuButton
                      asChild
                      isActive={navActive(pathname, "/institution/competitions")}
                      size="lg"
                      tooltip="Competitions"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/institution/competitions") &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/institution/competitions"
                        aria-current={
                          navActive(pathname, "/institution/competitions")
                            ? "page"
                            : undefined
                        }
                        data-testid="institution-nav-competitions"
                      >
                        <TrophyIcon />
                        <span>Competitions</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                    <SidebarMenuButton
                      asChild
                      isActive={navActive(pathname, "/institution/nominate")}
                      size="lg"
                      tooltip="Register competitor"
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !navActive(pathname, "/institution/nominate") &&
                          "text-sidebar-foreground/65",
                      )}
                    >
                      <Link
                        href="/institution/nominate"
                        aria-current={
                          navActive(pathname, "/institution/nominate")
                            ? "page"
                            : undefined
                        }
                        data-testid="institution-nav-nominate"
                      >
                        <UserPlusIcon />
                        <span>Register competitor</span>
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
                  Institution
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
                  data-testid="institution-nav-sign-out"
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
