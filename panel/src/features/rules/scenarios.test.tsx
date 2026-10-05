import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { MockRule } from "@/api/types"
import { db } from "@/mocks/db"
import { axe, renderRoute } from "@/test/render"

const DASHBOARD = "0192f5a0-0000-7000-8000-0000000a0001"

/** The dashboard rule with a second, failing scenario (PR-11). */
function withTwoScenarios(): MockRule {
  const rule = db.rules.find((r) => r.id === DASHBOARD)!
  const first = rule.responses[0]!
  rule.responses.push({ ...first, id: "0192f5a0-0000-7000-8000-0000000b0002", name: "outage", statusCode: 503 })
  return rule
}

const tab = (name: RegExp) => screen.findByRole("tab", { name })

describe("PR-11 scenarios", () => {
  it("shows a tab per scenario and marks the active one (axe clean)", async () => {
    withTwoScenarios()
    const { container } = renderRoute(`/rules/${DASHBOARD}`)
    const success = await tab(/success/)
    expect(success).toHaveAttribute("aria-selected", "true")
    expect(within(success).getByText("Active")).toBeInTheDocument()
    expect(within(await tab(/outage/)).queryByText("Active")).not.toBeInTheDocument()
    expect(screen.getByText("The Gateway serves this scenario.")).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("switching tabs shows that scenario's response, and the summary says it isn't active", async () => {
    withTwoScenarios()
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await tab(/outage/))
    expect(screen.getByLabelText("Scenario name")).toHaveValue("outage")
    expect(screen.getByLabelText("Status code")).toHaveValue("503")
    expect(screen.getByTestId("not-active-note")).toHaveTextContent("success")
  })

  it("Make active activates the selected scenario", async () => {
    const rule = withTwoScenarios()
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await tab(/outage/))
    await user.click(screen.getByRole("button", { name: "Make active" }))
    await waitFor(() => expect(rule.activeResponseId).toBe("0192f5a0-0000-7000-8000-0000000b0002"))
    expect(await screen.findByText("The Gateway serves this scenario.")).toBeInTheDocument()
    expect(within(await tab(/outage/)).getByText("Active")).toBeInTheDocument()
  })

  it("saving edits the selected scenario, not the active one", async () => {
    const rule = withTwoScenarios()
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await tab(/outage/))
    const status = screen.getByLabelText("Status code")
    await user.clear(status)
    await user.type(status, "504")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText("All changes saved")).toBeInTheDocument()
    expect(rule.responses.find((r) => r.name === "outage")?.statusCode).toBe(504)
    expect(rule.responses.find((r) => r.name === "success")?.statusCode).toBe(200)
    expect(rule.activeResponseId).toBe(rule.responses[0]!.id)
  })

  it("asks before dropping unsaved scenario edits when switching tabs", async () => {
    withTwoScenarios()
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.type(await screen.findByLabelText("Scenario name"), "-edited")
    await user.click(await tab(/outage/))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }))
    expect(screen.getByLabelText("Scenario name")).toHaveValue("success-edited")
    await user.click(await tab(/success/))
    await user.click(await tab(/outage/))
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard edits" }))
    expect(await screen.findByDisplayValue("outage")).toBeInTheDocument()
  })

  it("Duplicate scenario copies the selected one under a new name and shows it", async () => {
    const rule = db.rules.find((r) => r.id === DASHBOARD)!
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await screen.findByRole("button", { name: "Duplicate scenario" }))
    await waitFor(() => expect(rule.responses).toHaveLength(2))
    expect(rule.responses[1]).toMatchObject({ name: "success-copy", statusCode: 200 })
    await waitFor(async () => expect(await tab(/success-copy/)).toHaveAttribute("aria-selected", "true"))
    expect(screen.getByLabelText("Scenario name")).toHaveValue("success-copy")
    expect(rule.activeResponseId).toBe(rule.responses[0]!.id)
  })

  it("deletes a scenario after a confirm; the last scenario can't be deleted", async () => {
    const rule = withTwoScenarios()
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    await user.click(await tab(/outage/))
    await user.click(screen.getByRole("button", { name: "Delete scenario" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("Delete scenario “outage”?")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Delete scenario" }))
    await waitFor(() => expect(rule.responses).toHaveLength(1))
    expect(await screen.findByDisplayValue("success")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Delete scenario" })).toBeDisabled()
  })
})

describe("PR-19 body mode", () => {
  it("keeps a Template body a Template when the response is saved", async () => {
    const rule = db.rules.find((r) => r.id === DASHBOARD)!
    rule.responses[0]!.bodyMode = "Template"
    rule.responses[0]!.body = "Hello {{ request.query.name }}"
    const { user } = renderRoute(`/rules/${DASHBOARD}`)
    const modes = await screen.findByRole("radiogroup", { name: "Body mode" })
    expect(within(modes).getByRole("radio", { name: "Template" })).toBeChecked()
    await user.type(screen.getByLabelText("Scenario name"), "-v2")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText("All changes saved")).toBeInTheDocument()
    expect(rule.responses[0]).toMatchObject({ name: "success-v2", bodyMode: "Template" })
  })

  it("a Template body isn't held to JSON syntax", async () => {
    const { user } = renderRoute("/rules/new")
    await user.type(await screen.findByLabelText("Name"), "Greeting")
    await user.type(screen.getByLabelText("Pattern"), "/hello")
    await user.click(
      within(screen.getByRole("radiogroup", { name: "Body mode" })).getByRole("radio", { name: "Template" }),
    )
    await user.type(screen.getByLabelText("Body"), "{{{{ fake.name() }}")
    await user.click(screen.getByRole("button", { name: "Create rule" }))
    await waitFor(() => expect(db.rules.find((r) => r.name === "Greeting")?.responses[0]?.bodyMode).toBe("Template"))
  })
})

describe("rule state in the summary", () => {
  it("says a disabled rule is skipped, even though it has an active scenario", async () => {
    db.rules.find((r) => r.id === DASHBOARD)!.isEnabled = false
    renderRoute(`/rules/${DASHBOARD}`)
    expect(await screen.findByTestId("disabled-note")).toHaveTextContent("skipped")
  })

  it("says nothing about state for an enabled rule", async () => {
    renderRoute(`/rules/${DASHBOARD}`)
    await screen.findByTestId("rule-sentence")
    expect(screen.queryByTestId("disabled-note")).not.toBeInTheDocument()
  })
})
