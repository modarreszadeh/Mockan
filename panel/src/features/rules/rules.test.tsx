import { screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"
import { axe, renderRoute } from "@/test/render"

const rowOf = (name: string) => screen.getByRole("link", { name }).closest("tr")!

describe("SCR-04 Rules", () => {
  it("PR-05 lists rules in gateway precedence order (axe clean)", async () => {
    const { container } = renderRoute("/rules")
    await screen.findByText("Sorted by match precedence")
    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("link")[0]!.textContent)
    // priority 50 first; then Exact (longer pattern first), Template (older first), Prefix
    expect(names).toEqual([
      "Items not found",
      "Notifications outage",
      "Limsa dashboard",
      "Delete draft",
      "Order details",
      "Reports (all)",
    ])
    expect(await axe(container)).toHaveNoViolations()
  })

  it("PR-08 disabled rules stay listed, dimmed, and re-enable without opening", async () => {
    const { user, router } = renderRoute("/rules")
    await screen.findByText("Sorted by match precedence")
    const row = rowOf("Order details")
    expect(row).toHaveAttribute("data-disabled")
    expect(within(row).getByText("Off — proxied")).toBeInTheDocument()
    await user.click(within(row).getByRole("switch", { name: "Enable Order details" }))
    expect(router.state.location.pathname).toBe("/rules")
    await waitFor(() => expect(db.rules.find((r) => r.name === "Order details")?.isEnabled).toBe(true))
    expect(await screen.findByText("Saved — live in about 2 seconds")).toBeInTheDocument()
  })

  it("PR-07 rolls back an optimistic toggle and explains the error", async () => {
    server.use(
      http.post("*/api/v1/me/rules/:id/toggle", () =>
        HttpResponse.json({ title: "Gateway config store unavailable", detail: "Try again." }, { status: 503 }),
      ),
    )
    const { user } = renderRoute("/rules")
    await screen.findByText("Sorted by match precedence")
    await user.click(within(rowOf("Limsa dashboard")).getByRole("switch"))
    expect(await screen.findByText("Couldn't change the rule")).toBeInTheDocument()
    expect(within(rowOf("Limsa dashboard")).getByRole("switch")).toBeChecked()
  })

  it("row click opens the editor; the switch and row menu don't navigate", async () => {
    const { user, router } = renderRoute("/rules")
    await screen.findByText("Sorted by match precedence")
    await user.click(within(rowOf("Reports (all)")).getByRole("button", { name: "Actions for Reports (all)" }))
    expect(await screen.findByRole("menuitem", { name: "Duplicate" })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/rules")
    await user.keyboard("{Escape}")
    await user.click(within(rowOf("Reports (all)")).getByText("/limsa/api/v1/reports/"))
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/rules\/0192/))
  })

  it("filters by search text and keeps it in the URL", async () => {
    const { user, router } = renderRoute("/rules")
    await user.type(await screen.findByRole("searchbox", { name: "Search rules" }), "orders")
    expect(screen.getAllByRole("row")).toHaveLength(2)
    expect(router.state.location.search).toBe("?q=orders")
    await user.clear(screen.getByRole("searchbox", { name: "Search rules" }))
    await user.type(screen.getByRole("searchbox", { name: "Search rules" }), "zzz")
    expect(screen.getByText("No rules match these filters.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Clear filters" }))
    expect(screen.getAllByRole("row")).toHaveLength(7)
  })

  it("duplicates a rule as a disabled copy and deletes with a confirm", async () => {
    const { user } = renderRoute("/rules")
    await screen.findByText("Sorted by match precedence")
    await user.click(within(rowOf("Limsa dashboard")).getByRole("button", { name: /Actions/ }))
    await user.click(await screen.findByRole("menuitem", { name: "Duplicate" }))
    expect(await screen.findByRole("link", { name: "Limsa dashboard (copy)" })).toBeInTheDocument()
    expect(db.rules.find((r) => r.name === "Limsa dashboard (copy)")?.isEnabled).toBe(false)

    await user.click(within(rowOf("Limsa dashboard (copy)")).getByRole("button", { name: /Actions/ }))
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Delete “Limsa dashboard (copy)”?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Delete rule" }))
    await waitFor(() => expect(screen.queryByRole("link", { name: "Limsa dashboard (copy)" })).not.toBeInTheDocument())
    expect(db.rules).toHaveLength(6)
  })

  it("PR-08 disable all confirms, then every rule is off", async () => {
    const { user } = renderRoute("/rules")
    await user.click(await screen.findByRole("button", { name: "Disable all" }))
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Disable all" }))
    await waitFor(() => expect(db.rules.every((r) => !r.isEnabled)).toBe(true))
    expect(await screen.findByRole("button", { name: "Enable all" })).toBeInTheDocument()
  })

  it("PR-18 empty state uses the PRD copy (axe clean)", async () => {
    resetDb("empty")
    const { container } = renderRoute("/rules")
    expect(
      await screen.findByText("No rules yet — all traffic is proxied. Create your first mock."),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /Create your first mock|New rule/ })).toHaveLength(1)
    expect(await axe(container)).toHaveNoViolations()
  })
})
