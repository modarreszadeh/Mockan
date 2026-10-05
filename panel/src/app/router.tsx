/**
 * Route tree (docs/frontend/screens.md). Feature screens are lazy-loaded; `handle.crumb` feeds the header breadcrumb.
 * Phase 2 routes (/logs, /test-route) are in the navigation only because they work (prompt §2 rule 7).
 */
import { createBrowserRouter, type RouteObject } from "react-router"

import { PANEL_BASE_PATH, USE_MSW } from "@/lib/config"

import { AppShell, type RouteHandle } from "./app-shell"
import { AdminGate, AuthGate } from "./auth-gate"
import { FullPageLoading, NotFoundPage, RouteErrorPage } from "./system-pages"

const crumb = (label: string): RouteHandle => ({ crumb: label })

/**
 * Dev-only routes: the style guide, and (MSW only) the simulated SSO login. With `VITE_USE_MSW=false`
 * `/api/v1/auth/login` is not a Panel route: the Vite dev proxy sends it to the real Admin API.
 */
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: "__design",
        lazy: () => import("@/features/design/design-page").then((m) => ({ Component: m.DesignPage })),
      },
      ...(USE_MSW
        ? [
            {
              path: "api/v1/auth/login",
              lazy: () => import("./dev-login-page").then((m) => ({ Component: m.DevLoginPage })),
            },
          ]
        : []),
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
        path: "login",
        lazy: () => import("@/features/login/login-page").then((m) => ({ Component: m.LoginPage })),
      },
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
                path: "rules",
                handle: crumb("Rules"),
                children: [
                  {
                    index: true,
                    lazy: () => import("@/features/rules/rules-page").then((m) => ({ Component: m.RulesPage })),
                  },
                  {
                    path: "new",
                    handle: crumb("New rule"),
                    lazy: () =>
                      import("@/features/rules/rule-editor-page").then((m) => ({ Component: m.RuleEditorPage })),
                  },
                  {
                    path: ":ruleId",
                    handle: crumb("Edit rule"),
                    lazy: () =>
                      import("@/features/rules/rule-editor-page").then((m) => ({ Component: m.RuleEditorPage })),
                  },
                ],
              },
              {
                path: "logs",
                handle: crumb("Live log"),
                lazy: () => import("@/features/logs/logs-page").then((m) => ({ Component: m.LogsPage })),
              },
              {
                path: "test-route",
                handle: crumb("Test route"),
                lazy: () =>
                  import("@/features/test-route/test-route-page").then((m) => ({ Component: m.TestRoutePage })),
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
                children: [
                  {
                    path: "services",
                    handle: crumb("Service catalog"),
                    lazy: () =>
                      import("@/features/admin/service-catalog-page").then((m) => ({
                        Component: m.ServiceCatalogPage,
                      })),
                  },
                ],
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
