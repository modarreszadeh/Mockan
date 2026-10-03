import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { LOGIN_URL } from "@/api/client"
import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

describe("auth guard (prompt §5)", () => {
  it("redirects to SSO login on 401 with a full page navigation", async () => {
    resetDb("new") // signed out
    const assign = vi.fn()
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign, origin: "http://localhost:3000" })
    renderRoute("/")
    await waitFor(() => expect(assign).toHaveBeenCalledWith(LOGIN_URL))
  })

  it("PR-01 sends a Developer without a slug to onboarding from any route", async () => {
    resetDb("new")
    db.signedIn = true
    const { router } = renderRoute("/settings")
    expect(await screen.findByRole("heading", { name: "Claim your workspace" })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/onboarding")
  })

  it("shows a full-page explanation to a disabled Developer", async () => {
    resetDb("disabled")
    renderRoute("/")
    expect(await screen.findByRole("heading", { name: "Your workspace is disabled" })).toBeInTheDocument()
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument()
  })

  it("shows the problem and a retry when /me fails", async () => {
    resetDb("broken")
    renderRoute("/")
    expect(await screen.findByText("Mockan couldn't load this")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
  })
})

describe("AppShell", () => {
  it("shows the admin group only to admins and has no axe violations", async () => {
    const { container } = renderRoute("/")
    const nav = await screen.findByRole("link", { name: "Service catalog" })
    expect(nav).toBeInTheDocument()
    expect(screen.getByText("ehtesham", { selector: "span" })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("hides the admin group from non-admins", async () => {
    resetDb("member")
    renderRoute("/")
    await screen.findByRole("link", { name: "Rules" })
    expect(screen.queryByRole("link", { name: "Service catalog" })).not.toBeInTheDocument()
  })

  it("PR-08 kill switch confirms before turning off more than one rule", async () => {
    const { user } = renderRoute("/")
    const killSwitch = await screen.findByRole("switch", { name: "Mocks on" })
    await user.click(killSwitch)
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Turn off all 4 mocks?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Turn mocks off" }))
    await waitFor(() => expect(db.rules.every((r) => !r.isEnabled)).toBe(true))
    expect(await screen.findByRole("switch", { name: "Mocks off" })).not.toBeChecked()
  })
})
