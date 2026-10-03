/**
 * AppShell (prompt §4.6): `surface-soft` sidebar (icon rail < 1024 px, sheet < 768 px) and a 56 px header with
 * breadcrumb, workspace slug pill, MockKillSwitch and user menu.
 */
import {
  BlocksIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  ServerIcon,
  SettingsIcon,
  SlidersHorizontalIcon,
  type LucideIcon,
} from "lucide-react"
import { Fragment, useState, type ReactNode } from "react"
import { Link, NavLink, Outlet, useLocation, useMatches } from "react-router"

import { useLogout, useMe } from "@/api/queries/me"
import { MockKillSwitch, Wordmark } from "@/components/mockan"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
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
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import { useMediaQuery } from "@/hooks/use-mobile"

export interface RouteHandle {
  /** Breadcrumb label for this route. */
  crumb?: string
}

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

const MAIN_NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboardIcon, end: true },
  { to: "/rules", label: "Rules", icon: SlidersHorizontalIcon },
  { to: "/services", label: "Services", icon: ServerIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
]

// Phase 2 (SCR-09 Live log, SCR-10 Test route) are added here only when they work (prompt §2 rule 7).
const ADMIN_NAV: NavItem[] = [{ to: "/admin/services", label: "Service catalog", icon: BlocksIcon }]

function NavItems({ items }: { items: NavItem[] }) {
  const location = useLocation()
  const { isMobile, setOpenMobile } = useSidebar()
  return (
    <SidebarMenu>
      {items.map(({ to, label, icon: Icon, end }) => {
        const active = end
          ? location.pathname === to
          : location.pathname === to || location.pathname.startsWith(`${to}/`)
        return (
          <SidebarMenuItem key={to}>
            <SidebarMenuButton
              asChild
              isActive={active}
              tooltip={label}
              className="relative data-active:before:absolute data-active:before:inset-y-2 data-active:before:left-0 data-active:before:w-0.5 data-active:before:rounded-full data-active:before:bg-primary"
            >
              <NavLink to={to} end={end} onClick={() => isMobile && setOpenMobile(false)}>
                <Icon aria-hidden strokeWidth={1.75} />
                <span>{label}</span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        )
      })}
    </SidebarMenu>
  )
}

function AppSidebar({ isAdmin }: { isAdmin: boolean }) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 justify-center px-4 group-data-[collapsible=icon]:px-2">
        <Link
          to="/"
          aria-label="Mockan overview"
          className="rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        >
          <Wordmark className="group-data-[collapsible=icon]:hidden" />
          <span
            aria-hidden
            className="hidden size-8 items-center justify-center rounded-lg bg-surface-dark font-serif text-[18px] text-on-dark group-data-[collapsible=icon]:flex"
          >
            M
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <NavItems items={MAIN_NAV} />
          </SidebarGroupContent>
        </SidebarGroup>
        {isAdmin ? (
          <SidebarGroup>
            <SidebarGroupLabel className="type-overline text-muted-foreground">Admin</SidebarGroupLabel>
            <SidebarGroupContent>
              <NavItems items={ADMIN_NAV} />
            </SidebarGroupContent>
          </SidebarGroup>
        ) : null}
      </SidebarContent>
      <SidebarFooter className="px-4 pb-4 group-data-[collapsible=icon]:hidden">
        <p className="text-[12px] text-muted-foreground">Everything you don't mock is proxied.</p>
      </SidebarFooter>
    </Sidebar>
  )
}

function Breadcrumbs() {
  const matches = useMatches()
  const crumbs = matches
    .filter((m) => (m.handle as RouteHandle | undefined)?.crumb)
    .map((m) => ({ id: m.id, path: m.pathname, label: (m.handle as RouteHandle).crumb! }))
  if (crumbs.length === 0) return null
  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap">
        {crumbs.map((crumb, index) => (
          <Fragment key={crumb.id}>
            {index > 0 ? <BreadcrumbSeparator className="max-sm:hidden" /> : null}
            <BreadcrumbItem className={index < crumbs.length - 1 ? "hidden sm:inline-flex" : "min-w-0"}>
              {index === crumbs.length - 1 ? (
                <BreadcrumbPage className="truncate">{crumb.label}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link to={crumb.path}>{crumb.label}</Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]!.toUpperCase())
      .join("") || "?"
  )
}

function UserMenu({ displayName, slug }: { displayName: string; slug: string | null }) {
  const logout = useLogout()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label={`Account menu for ${displayName}`}>
          <Avatar className="size-8">
            <AvatarFallback className="bg-surface-card type-caption text-ink">{initials(displayName)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="space-y-0.5">
          <p className="type-caption text-ink">{displayName}</p>
          {slug ? <p className="font-mono text-[12px] font-normal text-muted-foreground">{slug}</p> : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings">
            <SettingsIcon aria-hidden />
            Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => logout.mutate()}>
          <LogOutIcon aria-hidden />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Sidebar open state: follows the 1024 px breakpoint until the user toggles it at the current width. */
function useResponsiveSidebar() {
  const isWide = useMediaQuery("(min-width: 1024px)")
  const [override, setOverride] = useState<{ wide: boolean; open: boolean } | null>(null)
  const open = override && override.wide === isWide ? override.open : isWide
  return { open, onOpenChange: (next: boolean) => setOverride({ wide: isWide, open: next }) }
}

export function AppShell({ children }: { children?: ReactNode }) {
  const me = useMe()
  const sidebar = useResponsiveSidebar()
  const developer = me.data
  if (!developer) return null

  return (
    <SidebarProvider open={sidebar.open} onOpenChange={sidebar.onOpenChange}>
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-canvas px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:ring-3 focus:ring-ring/30"
      >
        Skip to content
      </a>
      <AppSidebar isAdmin={developer.isAdmin} />
      <SidebarInset className="min-w-0 bg-background">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur sm:px-4">
          <SidebarTrigger className="size-9" aria-label="Toggle navigation" />
          <Separator orientation="vertical" className="mx-1 data-vertical:h-5 data-vertical:self-center" />
          <Breadcrumbs />
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {developer.slug ? (
              <span
                className="hidden h-7 items-center rounded-full bg-surface-card px-3 font-mono text-[13px] text-ink md:inline-flex"
                title="Your workspace slug"
              >
                {developer.slug}
              </span>
            ) : null}
            <MockKillSwitch />
            <UserMenu displayName={developer.displayName} slug={developer.slug} />
          </div>
        </header>
        {/* SidebarInset is the <main> landmark; this is the skip-link target. */}
        <div
          id="main"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1200px] px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8"
        >
          {children ?? <Outlet />}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
