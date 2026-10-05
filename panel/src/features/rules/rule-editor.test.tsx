import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { db, resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"
import { axe, renderRoute } from "@/test/render"

const DASHBOARD = "0192f5a0-0000-7000-8000-0000000a0001"

describe("SCR-05 Rule editor", () => {
  it("US-03 creates an Exact rule with a JSON body (axe clean)", async () => {
    resetDb("empty")
    const { user, router, container } = renderRoute("/rules/new")
    await user.type(await screen.findByLabelText("Name"), "Limsa dashboard")
    await user.type(screen.getByLabelText("Pattern"), "/limsa/api/v1/dashboard")
    fireEvent.change(await screen.findByLabelText("Response body"), { target: { value: '{"totals": {"samples": 1}}' } })
    expect(screen.getByTestId("rule-sentence")).toHaveTextContent(
      "GET requests to /limsa/api/v1/dashboard return 200 immediately.",
    )
    expect(screen.getByRole("region", { name: "Response headers preview" })).toHaveTextContent("X-Mockan-Source: mock")
    expect(await axe(container)).toHaveNoViolations()

    await user.click(screen.getByRole("button", { name: "Create rule" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/rules"))
    const rule = db.rules[0]!
    expect(rule).toMatchObject({
      name: "Limsa dashboard",
      method: "GET",
      matchType: "Exact",
      pattern: "/limsa/api/v1/dashboard",
    })
    expect(rule.responses[0]).toMatchObject({
      statusCode: 200,
      body: '{"totals": {"samples": 1}}',
      contentType: "application/json",
    })
  })

  it("PR-06 invalid JSON blocks save and shows line/column", async () => {
    const { user } = renderRoute("/rules/new")
    await user.type(await screen.findByLabelText("Name"), "Broken")
    await user.type(screen.getByLabelText("Pattern"), "/x")
    fireEvent.change(await screen.findByLabelText("Response body"), { target: { value: '{\n  "a": 1,\n}' } })
    await user.click(screen.getByRole("button", { name: "Create rule" }))
    expect((await screen.findAllByText(/^Line 3, Col 1:/)).length).toBeGreaterThan(0)
    expect(db.rules.find((r) => r.name === "Broken")).toBeUndefined()
  })

  it("PR-05 template rejects {*rest} in the middle on the pattern field", async () => {
    const { user } = renderRoute("/rules/new")
    await user.click(
      within(await screen.findByRole("radiogroup", { name: "Match type" })).getByRole("radio", { name: "Template" }),
    )
    await user.type(screen.getByLabelText("Pattern"), "/files/{{*rest}/meta")
    await user.type(screen.getByLabelText("Name"), "Files")
    await user.click(screen.getByRole("button", { name: "Create rule" }))
    expect(await screen.findByText("{*name} can only be the last segment.")).toBeInTheDocument()
    expect(screen.getByLabelText("Pattern")).toHaveAttribute("aria-invalid", "true")
  })

  it("TODO(OQ-F1) server validation errors land on the right field", async () => {
    server.use(
      http.post("*/api/v1/me/rules", () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ["body", "pattern"], msg: "RE2 can't compile this pattern: missing )", type: "value_error" },
              {
                loc: ["body", "responses", 0, "status_code"],
                msg: "Status code must be between 100 and 599.",
                type: "value_error",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    )
    const { user } = renderRoute("/rules/new")
    await user.type(await screen.findByLabelText("Name"), "Server says no")
    await user.type(screen.getByLabelText("Pattern"), "/ok")
    await user.click(screen.getByRole("button", { name: "Create rule" }))
    expect(await screen.findByText("RE2 can't compile this pattern: missing )")).toBeInTheDocument()
    expect(screen.getByText("Status code must be between 100 and 599.")).toBeInTheDocument()
    expect(screen.getByLabelText("Pattern")).toHaveFocus()
  })

  it("edits a rule's match and response and saves", async () => {
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    const name = await screen.findByLabelText("Name")
    expect(name).toHaveValue("Limsa dashboard")
    await user.clear(name)
    await user.type(name, "Dashboard v2")
    const status = screen.getByLabelText("Status code")
    await user.clear(status)
    await user.type(status, "503")
    await user.click(screen.getByRole("button", { name: "3 s" }))
    expect(screen.getByTestId("rule-sentence")).toHaveTextContent("return 503 after 3 s.")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText("Saved — live in about 2 seconds")).toBeInTheDocument()
    const rule = db.rules.find((r) => r.id === DASHBOARD)!
    expect(rule.name).toBe("Dashboard v2")
    expect(rule.responses[0]).toMatchObject({ statusCode: 503, delayMs: 3000 })
    expect(await screen.findByText("All changes saved")).toBeInTheDocument()
  })

  it("asks before leaving with unsaved changes", async () => {
    const { user, router } = renderRoute(`/rules/${DASHBOARD}`)
    await user.type(await screen.findByLabelText("Name"), " (edited)")
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Discard unsaved changes?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }))
    expect(router.state.location.pathname).toBe(`/rules/${DASHBOARD}`)
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard changes" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/rules"))
  })

  it("deletes from the Danger zone with a confirm", async () => {
    const { user, router } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await screen.findByRole("button", { name: "Delete rule" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Delete “Limsa dashboard”?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Delete rule" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/rules"))
    expect(db.rules.find((r) => r.id === DASHBOARD)).toBeUndefined()
  })

  it("explains a rule that doesn't exist", async () => {
    renderRoute("/rules/0192f5a0-0000-7000-8000-00000000dead")
    expect(await screen.findByText("This rule doesn't exist")).toBeInTheDocument()
  })

  it("plain-text content types get a textarea instead of the JSON editor", async () => {
    const { user } = renderRoute("/rules/new")
    const contentType = await screen.findByLabelText("Content type")
    await user.clear(contentType)
    await user.type(contentType, "text/plain")
    expect(screen.queryByTestId("json-editor")).not.toBeInTheDocument()
    expect(screen.getByLabelText("Body").tagName).toBe("TEXTAREA")
  })
})
