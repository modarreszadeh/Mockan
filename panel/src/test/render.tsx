/** Render helpers: the real route tree in a memory router with a fresh QueryClient and MSW. */
import { QueryClient } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { axe as runAxe } from "vitest-axe"

import { Providers } from "@/app/providers"
import { routes } from "@/app/router"

export function testQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
}

/** Render the app at `path` (e.g. "/rules"). */
export function renderRoute(path: string) {
  const queryClient = testQueryClient()
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const user = userEvent.setup()
  const utils = render(
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>,
  )
  return { ...utils, user, router, queryClient }
}

/** Render a single component with providers (no router). */
export function renderWithProviders(ui: ReactElement) {
  const queryClient = testQueryClient()
  const user = userEvent.setup()
  return { ...render(<Providers queryClient={queryClient}>{ui}</Providers>), user, queryClient }
}

/** axe with rules that jsdom can't evaluate turned off (colour contrast needs real layout). */
export const axe = (container: Element) =>
  runAxe(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } })
