import { createBrowserRouter, type RouteObject } from "react-router"

import { PANEL_BASE_PATH } from "@/lib/config"

export const routes: RouteObject[] = [
  { path: "/", element: <p className="p-8">Mockan Panel</p> },
  ...(import.meta.env.DEV
    ? [
        {
          path: "/__design",
          lazy: () => import("@/features/design/design-page").then((m) => ({ Component: m.DesignPage })),
        },
      ]
    : []),
]

export function createAppRouter() {
  // TODO(OQ-03): basename follows VITE_PANEL_BASE_PATH (default "/").
  return createBrowserRouter(routes, { basename: PANEL_BASE_PATH.replace(/\/$/, "") || "/" })
}
