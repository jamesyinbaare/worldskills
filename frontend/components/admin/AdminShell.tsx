"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2Icon,
  CalendarIcon,
  ClipboardListIcon,
  EllipsisIcon,
  LayoutDashboardIcon,
  LayersIcon,
  LogOutIcon,
  ScaleIcon,
  ScrollTextIcon,
  SettingsIcon,
  ShapesIcon,
  TrophyIcon,
  UsersIcon,
  UsersRoundIcon,
  ClipboardCheckIcon,
} from "lucide-react";
import { CrestLogo } from "@/components/brand/LogoMark";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { isSuperAdminRole } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin", label: "Overview", icon: LayoutDashboardIcon, exact: true },
  { href: "/admin/competitions", label: "Competitions", icon: ClipboardListIcon },
  { href: "/admin/competitors", label: "Competitors", icon: UsersRoundIcon },
  { href: "/admin/families", label: "Families", icon: ShapesIcon },
  { href: "/admin/skills", label: "Skills", icon: LayersIcon },
] as const;

const RUN_NAV = [
  { href: "/admin/schedule", label: "Schedule", icon: CalendarIcon },
  { href: "/admin/scoring", label: "Scoring", icon: ClipboardCheckIcon },
  { href: "/admin/results", label: "Results", icon: TrophyIcon },
  { href: "/admin/appeals", label: "Appeals", icon: ScaleIcon },
] as const;

const MORE_NAV = [
  { href: "/admin/institutions", label: "Institutions", icon: Building2Icon },
  { href: "/admin/users", label: "Users", icon: UsersIcon },
  { href: "/admin/settings", label: "Settings", icon: SettingsIcon },
  { href: "/admin/audit", label: "Audit", icon: ScrollTextIcon },
] as const;

function roleCaption(role: string): string {
  return isSuperAdminRole(role) ? "Super Admin" : "Administrator";
}

function navActive(pathname: string, href: string, exact?: boolean): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { me, logout } = useAuth();
  const moreActive = MORE_NAV.some((item) => navActive(pathname, item.href));

  return (
    <div className="admin-shell min-h-svh bg-[var(--admin-canvas)]">
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
                  Admin console
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
                  {NAV.map((item) => {
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

            <SidebarGroup className="mt-4 px-1 group-data-[collapsible=icon]:px-0">
              <SidebarGroupLabel className="mb-2 px-3 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Run competition
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
                  {RUN_NAV.map((item) => {
                    const active = navActive(pathname, item.href);
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
          </SidebarContent>

          <SidebarFooter className="gap-3 border-t border-sidebar-border/70 p-3 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:px-1.5">
            {me ? (
              <div className="rounded-2xl bg-muted/80 px-3 py-3 group-data-[collapsible=icon]:hidden">
                <p className="truncate text-sm font-semibold text-sidebar-foreground">
                  {me.full_name ?? me.email}
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {roleCaption(me.role)}
                </p>
              </div>
            ) : null}
            <SidebarMenu className="gap-2 group-data-[collapsible=icon]:items-center">
              <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <SidebarMenuButton
                      size="lg"
                      tooltip="More"
                      isActive={moreActive}
                      className={cn(
                        "rounded-2xl px-3 font-medium",
                        !moreActive && "text-sidebar-foreground/65",
                      )}
                      data-testid="admin-nav-more"
                    >
                      <EllipsisIcon />
                      <span>More</span>
                    </SidebarMenuButton>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    side="top"
                    align="start"
                    className="w-52"
                  >
                    <DropdownMenuLabel>Administration</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {MORE_NAV.map((item) => {
                      const Icon = item.icon;
                      const active = navActive(pathname, item.href);
                      return (
                        <DropdownMenuItem key={item.href} asChild>
                          <Link
                            href={item.href}
                            aria-current={active ? "page" : undefined}
                            className={cn(active && "bg-accent")}
                          >
                            <Icon className="size-4" />
                            {item.label}
                          </Link>
                        </DropdownMenuItem>
                      );
                    })}
                  </DropdownMenuContent>
                </DropdownMenu>
              </SidebarMenuItem>
              <SidebarMenuItem className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center">
                <SidebarMenuButton
                  size="lg"
                  tooltip="Sign out"
                  className="rounded-2xl px-3 text-sidebar-foreground/70 hover:text-destructive"
                  onClick={logout}
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
