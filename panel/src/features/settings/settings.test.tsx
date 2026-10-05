import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { db } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

describe("SCR-08 Settings", () => {
  it("PR-03 shows the read-only slug and saves display name and origins (axe clean)", async () => {
    const { user, container } = renderRoute("/settings")
    const slug = await screen.findByLabelText("Workspace slug")
    expect(slug).toHaveAttribute("readonly")
    expect(await axe(container)).toHaveNoViolations()

    const name = screen.getByLabelText("Display name")
    await user.clear(name)
    await user.type(name, "Ehtesham K.")
    await user.click(screen.getByRole("button", { name: "Add origin" }))
    await user.type(screen.getByLabelText("Allowed origin 3"), "http://localhost:5173")
    await user.click(screen.getByRole("button", { name: "Save settings" }))

    expect(await screen.findByText("Saved — live in about 2 seconds")).toBeInTheDocument()
    expect(db.developer.displayName).toBe("Ehtesham K.")
    expect(db.developer.allowedOrigins).toEqual(["http://localhost:*", "http://127.0.0.1:*", "http://localhost:5173"])
  })

  it("validates origins inline", async () => {
    const { user } = renderRoute("/settings")
    const first = await screen.findByLabelText("Allowed origin 1")
    await user.clear(first)
    await user.type(first, "localhost:3000")
    await user.click(screen.getByRole("button", { name: "Save settings" }))
    expect(await screen.findByText("Start with http:// or https://.")).toBeInTheDocument()
  })

  it("US-54 asks before saving an empty origins list, and resets to defaults", async () => {
    const { user } = renderRoute("/settings")
    await user.click(await screen.findByRole("button", { name: "Remove allowed origin 2" }))
    await user.click(screen.getByRole("button", { name: "Remove allowed origin 1" }))
    await user.click(screen.getByRole("button", { name: "Save settings" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText(/Browser calls will fail CORS/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(db.developer.allowedOrigins).toHaveLength(2)

    await user.click(screen.getByRole("button", { name: "Reset to defaults" }))
    expect(screen.getByLabelText("Allowed origin 1")).toHaveValue("http://localhost:*")
    expect(screen.getByLabelText("Allowed origin 2")).toHaveValue("http://127.0.0.1:*")
  })

  it("saves an empty list after confirming", async () => {
    const { user } = renderRoute("/settings")
    await user.click(await screen.findByRole("button", { name: "Remove allowed origin 2" }))
    await user.click(screen.getByRole("button", { name: "Remove allowed origin 1" }))
    await user.click(screen.getByRole("button", { name: "Save settings" }))
    await user.click(await screen.findByRole("button", { name: "Save anyway" }))
    await waitFor(() => expect(db.developer.allowedOrigins).toEqual([]))
  })
})
