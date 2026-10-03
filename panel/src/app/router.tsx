/**
 * Route tree (Frontend/screens.md). Feature screens are lazy-loaded; `handle.crumb` feeds the header breadcrumb.
 * Phase 2 routes (/logs, /test-route) are added only when they work.
 */
import { createBrowserRouter, type RouteObject } from "react-router"

import { PANEL_BASE_PATH } from "@/lib/config"

import { AppShell, type RouteHandle } from "./app-shell"
import { AdminGate, AuthGate } from "./auth-gate"
import { FullPageLoading, NotFoundPage, RouteErrorPage } from "./system-pages"

const crumb = (label: string): RouteHandle => ({ crumb: label })

/** Dev-only routes: the style guide, and the simulated SSO login used by the MSW backend. */
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: "__design",
        lazy: () => import("@/features/design/design-page").then((m) => ({ Component: m.DesignPage })),
      },
      {
        path: "api/v1/auth/login",
        lazy: () => import("./dev-login-page").then((m) => ({ Component: m.DevLoginPage })),
      },
    ]
  : []

export const routes: RouteObject[] = [
  {
    path: "/",
    errorElement: <RouteErrorPage />,
    HydrateFallback: FullPageLoading,
    children: [
      ...devRoutes,
      {
        element: <AuthGate />,
        children: [
          {
            path: "onboarding",
            lazy: () => import("@/features/onboarding/onboarding-page").then((m) => ({ Component: m.OnboardingPage })),
          },
          {
            element: <AppShell />,
            handle: crumb("Mockan"),
            children: [
              {
                index: true,
                handle: crumb("Overview"),
                lazy: () => import("@/features/overview/overview-page").then((m) => ({ Component: m.OverviewPage })),
              },
              {
                path: "services",
                handle: crumb("Services"),
                lazy: () => import("@/features/services/services-page").then((m) => ({ Component: m.ServicesPage })),
              },
              {
                path: "settings",
                handle: crumb("Settings"),
                lazy: () => import("@/features/settings/settings-page").then((m) => ({ Component: m.SettingsPage })),
              },
              {
                path: "admin",
                element: <AdminGate />,
                children: [],
              },
              { path: "*", element: <NotFoundPage /> },
            ],
          },
        ],
      },
    ],
  },
]

export function createAppRouter() {
  // TODO(OQ-03): basename follows VITE_PANEL_BASE_PATH (default "/").
  return createBrowserRouter(routes, { basename: PANEL_BASE_PATH.replace(/\/$/, "") || "/" })
}
