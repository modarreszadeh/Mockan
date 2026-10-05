import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { LOGIN_PAGE_URL, LOGIN_URL } from "@/api/client"
import { meKeys } from "@/api/queries/keys"
import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

/** jsdom can't navigate: stop the anchor's default action so a click is observable without an error. */
function blockNavigation() {
  const stop = (event: Event) => event.preventDefault()
  document.addEventListener("click", stop)
  return () => document.removeEventListener("click", stop)
}

describe("SCR-01 Login", () => {
  const assign = vi.fn()

  // The memory router doesn't move the browser: say the browser is on /login, as it is for real.
  beforeEach(() => {
    assign.mockClear()
    vi.spyOn(window, "location", "get").mockReturnValue({
      ...window.location,
      pathname: LOGIN_PAGE_URL,
      assign,
      origin: "http://localhost:3000",
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it("offers single sign-on with Keycloak, with a key icon, and has no violations", async () => {
    resetDb("new") // signed out
    const { container } = renderRoute("/login")

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in to Mockan" })).toBeInTheDocument()
    const link = screen.getByRole("link", { name: "Sign in with Keycloak" })
    expect(link).toHaveAttribute("href", LOGIN_URL)
    expect(link.querySelector("svg.lucide-key-round")).toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument() // SSO only
    expect(await axe(container)).toHaveNoViolations()
  })

  it("shows a pending state after the click and ignores a second click", async () => {
    resetDb("new")
    const unblock = blockNavigation()
    const { user } = renderRoute("/login")

    await user.click(await screen.findByRole("link", { name: "Sign in with Keycloak" }))
    const pending = await screen.findByRole("link", { name: "Redirecting to Keycloak…" })
    expect(pending).toHaveAttribute("aria-disabled", "true")
    expect(screen.getByRole("status")).toBeInTheDocument()

    const notPrevented = fireEvent.click(pending)
    expect(notPrevented).toBe(false) // preventDefault was called: no second login starts
    unblock()
  })

  it("restores the button when the browser brings the page back from the cache", async () => {
    resetDb("new")
    const unblock = blockNavigation()
    const { user } = renderRoute("/login")
    await user.click(await screen.findByRole("link", { name: "Sign in with Keycloak" }))
    expect(await screen.findByRole("link", { name: "Redirecting to Keycloak…" })).toBeInTheDocument()

    const back = new Event("pageshow") as PageTransitionEvent
    Object.defineProperty(back, "persisted", { value: true })
    window.dispatchEvent(back)

    expect(await screen.findByRole("link", { name: "Sign in with Keycloak" })).toBeInTheDocument()
    unblock()
  })

  it("sends an already signed-in Developer to the app", async () => {
    resetDb("default")
    db.signedIn = true
    const { router } = renderRoute("/login")
    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
  })

  it("is where Sign out ends, so Keycloak's still-open SSO session doesn't sign the user straight back in", async () => {
    resetDb("disabled") // its full-page notice has a Sign out button
    const { user } = renderRoute("/")
    await user.click(await screen.findByRole("button", { name: "Sign out" }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith(LOGIN_PAGE_URL))
    expect(assign).not.toHaveBeenCalledWith(LOGIN_URL)
    expect(db.signedIn).toBe(false)
  })

  it("does not redirect-loop: a 401 on the login page itself stays on the page", async () => {
    resetDb("new")
    const { queryClient } = renderRoute("/login")
    await screen.findByRole("heading", { name: "Sign in to Mockan" })
    await waitFor(() => expect(queryClient.getQueryState(meKeys.all)?.status).toBe("error")) // the 401 happened
    expect(assign).not.toHaveBeenCalled()
  })
})
