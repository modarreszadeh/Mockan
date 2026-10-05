import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

const openService = async (user: ReturnType<typeof renderRoute>["user"], name: string) => {
  await user.click(await screen.findByText(name, { selector: "td" }))
  return screen.findByRole("dialog", { name: `Edit ${name}` })
}

describe("SCR-07 Service catalog (admin)", () => {
  it("PR-10 non-admins get a 403 page", async () => {
    resetDb("member")
    renderRoute("/admin/services")
    expect(await screen.findByRole("heading", { name: "Admins only" })).toBeInTheDocument()
  })

  it("lists Services with their environments (axe clean)", async () => {
    const { container } = renderRoute("/admin/services")
    const row = (await screen.findByText("portal", { selector: "td" })).closest("tr")!
    expect(within(row).getByText("https://portal.stage.internal/api")).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("PR-15 a non-allowlisted base URL is rejected inline on the field", async () => {
    const { user } = renderRoute("/admin/services")
    const sheet = await openService(user, "limsa")
    const baseUrl = within(sheet).getAllByLabelText("Base URL")[0]!
    await user.clear(baseUrl)
    await user.type(baseUrl, "https://limsa.prod.internal")
    await user.click(within(sheet).getByRole("button", { name: "Save Service" }))
    expect(
      await within(sheet).findByText("Only allowlisted dev/stage hosts can be used.", { selector: "p[id]" }),
    ).toBeInTheDocument()
    expect(baseUrl).toHaveAttribute("aria-invalid", "true")
    expect(db.services.find((s) => s.name === "limsa")!.environments[0]!.baseUrl).toBe("https://limsa.dev.internal")
  })

  it("PR-10 duplicate name and path prefix errors appear on the fields", async () => {
    const { user } = renderRoute("/admin/services")
    const sheet = await openService(user, "portal")
    const name = within(sheet).getByLabelText("Name")
    await user.clear(name)
    await user.type(name, "limsa")
    await user.click(within(sheet).getByRole("button", { name: "Save Service" }))
    expect(await within(sheet).findByText("A Service named “limsa” already exists.")).toBeInTheDocument()

    await user.clear(name)
    await user.type(name, "portal")
    const prefix = within(sheet).getByLabelText("Path prefix")
    await user.clear(prefix)
    await user.type(prefix, "/identity")
    await user.click(within(sheet).getByRole("button", { name: "Save Service" }))
    expect(
      await within(sheet).findByText("Path prefix /identity is already used by another Service."),
    ).toBeInTheDocument()
  })

  it("PR-04 accepts “/” as the path prefix (a catch-all Service)", async () => {
    const { user } = renderRoute("/admin/services")
    await user.click(await screen.findByRole("button", { name: "Add Service" }))
    const sheet = await screen.findByRole("dialog", { name: "Add a Service" })
    await user.type(within(sheet).getByLabelText("Name"), "gateway")
    expect(within(sheet).getByLabelText("Path prefix")).toHaveValue("/") // the form's default
    await user.type(within(sheet).getByLabelText("Base URL"), "https://api.stage.internal")
    await user.click(within(sheet).getByRole("button", { name: "Create Service" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(db.services.find((s) => s.name === "gateway")?.pathPrefix).toBe("/")
  })

  it("US-30 creates a Service with a stage environment", async () => {
    const { user } = renderRoute("/admin/services")
    await user.click(await screen.findByRole("button", { name: "Add Service" }))
    const sheet = await screen.findByRole("dialog", { name: "Add a Service" })
    await user.type(within(sheet).getByLabelText("Name"), "billing")
    const prefix = within(sheet).getByLabelText("Path prefix")
    await user.clear(prefix)
    await user.type(prefix, "/billing")
    await user.type(within(sheet).getByLabelText("Base URL"), "https://billing.stage.internal")
    await user.click(within(sheet).getByRole("button", { name: "Create Service" }))
    expect(await screen.findByText("billing", { selector: "td" })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    const billing = db.services.find((s) => s.name === "billing")!
    expect(billing.environments).toMatchObject([
      { environment: "stage", baseUrl: "https://billing.stage.internal", timeoutSeconds: 100 },
    ])
  })

  it("deletes with a confirm naming the Service", async () => {
    const { user } = renderRoute("/admin/services")
    const row = (await screen.findByText("portal", { selector: "td" })).closest("tr")!
    await user.click(within(row).getByRole("button", { name: "Actions for portal" }))
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Delete Service “portal”?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Delete portal" }))
    await waitFor(() => expect(db.services.some((s) => s.name === "portal")).toBe(false))
  })
})
