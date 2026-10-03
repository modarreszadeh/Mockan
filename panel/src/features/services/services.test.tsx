import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

describe("SCR-06 Services", () => {
  it("PR-04 lists Services with the selected environment and upstream (axe clean)", async () => {
    const { container } = renderRoute("/services")
    const row = (await screen.findByText("limsa")).closest("tr")!
    expect(within(row).getByText("/limsa")).toBeInTheDocument()
    expect(within(row).getByText("https://limsa.dev.internal")).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("PR-04 a Service with one environment shows text, not a select", async () => {
    renderRoute("/services")
    const row = (await screen.findByText("portal")).closest("tr")!
    expect(within(row).queryByRole("combobox")).not.toBeInTheDocument()
    expect(within(row).getByText("stage")).toBeInTheDocument()
  })

  it("PR-04 changing the environment saves immediately with a toast", async () => {
    const { user } = renderRoute("/services")
    await user.click(await screen.findByRole("combobox", { name: "Environment for identity" }))
    await user.click(await screen.findByRole("option", { name: /dev/ }))
    expect(await screen.findByText("identity now proxies to dev — live in about 2 seconds")).toBeInTheDocument()
    const identity = db.services.find((s) => s.name === "identity")!
    await waitFor(() =>
      expect(db.serviceSettings.find((s) => s.serviceId === identity.id)?.serviceEnvironmentId).toBe(
        identity.environments.find((e) => e.environment === "dev")!.id,
      ),
    )
    const row = screen.getByText("identity").closest("tr")!
    expect(within(row).getByText("https://identity.dev.internal")).toBeInTheDocument()
  })

  it("PR-10 non-admins see no catalog edit controls", async () => {
    resetDb("member")
    renderRoute("/services")
    await screen.findByText("limsa")
    expect(screen.queryByRole("link", { name: "Manage catalog" })).not.toBeInTheDocument()
  })

  it("empty catalog explains the next step (axe clean)", async () => {
    resetDb("member")
    db.services = []
    const { container } = renderRoute("/services")
    expect(await screen.findByText("No Services in the catalog yet")).toBeInTheDocument()
    expect(screen.getByText(/Ask a Mockan admin/)).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
