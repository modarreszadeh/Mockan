import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

describe("SCR-03 Overview", () => {
  it("PR-18 shows greeting, base URL, stats and active mocks (axe clean)", async () => {
    const { container } = renderRoute("/")
    expect(await screen.findByRole("heading", { level: 1, name: /, Ehtesham$/ })).toBeInTheDocument()
    expect(screen.getByText("4 mocks active · everything else is proxied to the real backend.")).toBeInTheDocument()
    expect(screen.getByTestId("env-line")).toHaveTextContent("VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham")
    expect(screen.getByText("1 on dev")).toBeInTheDocument()
    const list = screen.getByRole("region", { name: "Active mocks" })
    expect(within(list).getAllByRole("switch")).toHaveLength(4)
    expect(await axe(container)).toHaveNoViolations()
  })

  it("US-53 empty workspace shows the PRD empty state and the checklist (axe clean)", async () => {
    resetDb("empty")
    const { container } = renderRoute("/")
    expect(
      await screen.findByText("No rules yet — all traffic is proxied. Create your first mock."),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Create your first mock" })).toHaveAttribute("href", "/rules/new")
    expect(screen.getByRole("heading", { name: "Getting started" })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: /Claim your slug/ })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: /Create your first mock/ })).not.toBeChecked()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("PR-08 toggling a rule here uses the shared mutation and stays visible", async () => {
    const { user } = renderRoute("/")
    const toggle = await screen.findByRole("switch", { name: "Disable Limsa dashboard" })
    await user.click(toggle)
    expect(await screen.findByRole("switch", { name: "Enable Limsa dashboard" })).not.toBeChecked()
    await waitFor(() => expect(db.rules.find((r) => r.name === "Limsa dashboard")?.isEnabled).toBe(false))
    expect(await screen.findByText("Saved — live in about 2 seconds")).toBeInTheDocument()
  })

  it("keeps manual checklist ticks and hides the card when everything is done", async () => {
    const { user } = renderRoute("/")
    await user.click(await screen.findByRole("checkbox", { name: /Point .env at Mockan/ }))
    expect(localStorage.getItem(`mockan.checklist.${db.developer.id}`)).toContain("env")
    await user.click(screen.getByRole("checkbox", { name: /Check X-Mockan-Source/ }))
    expect(screen.queryByRole("heading", { name: "Getting started" })).not.toBeInTheDocument()
  })
})

describe("SCR-03 Overview errors", () => {
  it("renders ProblemAlert + retry when rules fail", async () => {
    const { http, HttpResponse } = await import("msw")
    const { server } = await import("@/mocks/server")
    server.use(
      http.get("*/api/v1/me/rules", () =>
        HttpResponse.json({ title: "Rules are down", code: "internal_error" }, { status: 500 }),
      ),
    )
    renderRoute("/")
    expect(await screen.findByText("Rules are down")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
  })
})
