import { screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

beforeEach(() => {
  resetDb("new")
  db.signedIn = true
})

describe("SCR-02 Onboarding", () => {
  it("PR-01 shows why a slug is invalid before submit, keeps submit enabled and refocuses the field", async () => {
    const { user, container } = renderRoute("/onboarding")
    const input = await screen.findByLabelText("Workspace slug")
    expect(await axe(container)).toHaveNoViolations()

    await user.clear(input)
    await user.type(input, "Api")
    expect(await screen.findByText("Use lowercase letters only.")).toBeInTheDocument()
    await user.clear(input)
    await user.type(input, "api")
    expect(await screen.findByText("“api” is reserved. Pick another slug.")).toBeInTheDocument()

    const submit = screen.getByRole("button", { name: /Continue/ })
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(input).toHaveFocus()
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
  })

  it("PR-01 shows a taken slug inline under the field", async () => {
    const { user } = renderRoute("/onboarding")
    const input = await screen.findByLabelText("Workspace slug")
    await user.clear(input)
    await user.type(input, "qoolak")
    await user.click(screen.getByRole("button", { name: /Continue/ }))
    await user.click(await screen.findByRole("button", { name: "Claim slug" }))
    expect(await screen.findByText("“qoolak” is already taken. Try another one.")).toBeInTheDocument()
    expect(input).toHaveFocus()
    expect(db.developer.slug).toBeNull()
  })

  it("PR-18 says the slug can't be changed, then shows a copyable .env line", async () => {
    const { user, container } = renderRoute("/onboarding")
    const input = await screen.findByLabelText("Workspace slug")
    expect(input).toHaveValue("ehtesham") // suggested from the display name
    expect(screen.getByTestId("base-url-preview")).toHaveTextContent("https://mock.novin-tools.com/ehtesham")

    await user.click(screen.getByRole("button", { name: /Continue/ }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("cannot be changed later")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Claim slug" }))

    expect(await screen.findByRole("heading", { name: "You're all set, Ehtesham" })).toBeInTheDocument()
    expect(screen.getByTestId("env-line")).toHaveTextContent("VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham")
    await user.click(screen.getByRole("button", { name: "Copy .env line" }))
    expect(await screen.findByRole("button", { name: "Copied .env line" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Create your first mock" })).toHaveAttribute("href", "/rules/new")
    await waitFor(() => expect(db.developer.slug).toBe("ehtesham"))
    expect(await axe(container)).toHaveNoViolations()
  })

  it("sends an onboarded Developer back to the overview", async () => {
    resetDb("default")
    const { router } = renderRoute("/onboarding")
    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
  })
})
