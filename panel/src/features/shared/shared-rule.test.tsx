import { screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"

import type { MockResponse } from "@/api/types"
import { db } from "@/mocks/db"
import { server } from "@/mocks/server"
import { axe, renderRoute } from "@/test/render"

const TOKEN = "k3J9-wQz_0aBcDeFgHiJkLmNoPqRsTuV"

function shareRule(name: string) {
  const rule = db.rules.find((r) => r.name === name)!
  rule.shareToken = TOKEN
  return rule
}

const scenario = (rule: { id: string }, over: Partial<MockResponse>): MockResponse => ({
  id: crypto.randomUUID(),
  ruleId: rule.id,
  name: "scenario",
  statusCode: 200,
  headers: {},
  contentType: "application/json",
  body: "",
  bodyMode: "Static",
  delayMs: 0,
  createdAt: "2026-09-01T08:00:00.000Z",
  updatedAt: "2026-09-01T08:00:00.000Z",
  ...over,
})

describe("SCR-11 Shared rule", () => {
  it("S-3 shows the rule to a visitor who isn't signed in: request details and the active scenario (axe clean)", async () => {
    db.signedIn = false // no session at all: the page must not need one, nor bounce to the login page
    shareRule("Limsa dashboard")
    const { container, router } = renderRoute(`/shared/${TOKEN}`)

    expect(await screen.findByRole("heading", { level: 1, name: "Limsa dashboard" })).toBeInTheDocument()
    expect(screen.getByText("Read-only preview")).toBeInTheDocument()
    expect(screen.getByText("Ehtesham")).toBeInTheDocument() // Shared by …
    const request = screen.getByRole("region", { name: "Request" })
    expect(within(request).getByText("GET")).toBeInTheDocument()
    expect(within(request).getByText("Exact")).toBeInTheDocument()
    expect(within(request).getByText("/limsa/api/v1/dashboard", { selector: "code" })).toBeInTheDocument()
    expect(within(request).getByText("limsa")).toBeInTheDocument()
    expect(within(request).getByText("Enabled")).toBeInTheDocument()
    expect(within(request).getAllByText("None")).toHaveLength(2) // no query or header conditions
    expect(within(request).getByText(/\/ehtesham\/limsa\/api\/v1\/dashboard$/)).toBeInTheDocument()

    const scenarios = screen.getByRole("region", { name: "Scenarios" })
    expect(within(scenarios).getByRole("tab", { name: /success/ })).toHaveAttribute("aria-selected", "true")
    expect(within(scenarios).getByText("Active")).toBeInTheDocument()
    expect(within(scenarios).getByText(/OK/)).toBeInTheDocument()
    expect(within(scenarios).getByText("300 ms")).toBeInTheDocument()
    expect(document.title).toBe("Limsa dashboard · Mockan")
    expect(document.head.querySelector('meta[name="robots"][content="noindex"]')).not.toBeNull()
    expect(router.state.location.pathname).toBe(`/shared/${TOKEN}`)
    expect(await axe(container)).toHaveNoViolations()
  })

  it("shows conditions, every scenario with its headers and a pretty-printed body", async () => {
    const rule = shareRule("Notifications outage")
    rule.queryConditions = [{ key: "page", operator: "exists" }]
    rule.responses.push(
      scenario(rule, {
        name: "created",
        statusCode: 201,
        headers: { "X-Trace": "abc", Location: "/orders/1" },
        body: '{"id":1,"ok":true}',
        delayMs: 1500,
      }),
    )
    const { user } = renderRoute(`/shared/${TOKEN}`)
    await screen.findByRole("heading", { level: 1, name: "Notifications outage" })

    const request = screen.getByRole("region", { name: "Request" })
    expect(within(request).getByText("Disabled — requests are proxied")).toBeInTheDocument()
    const queries = within(request).getByRole("table", { name: "Query conditions" })
    expect(within(queries).getByText("page")).toBeInTheDocument()
    expect(within(queries).getByText("is present")).toBeInTheDocument()
    const headers = within(request).getByRole("table", { name: "Header conditions" })
    expect(within(headers).getByText("X-Feature")).toBeInTheDocument()
    expect(within(headers).getByText("beta")).toBeInTheDocument()

    expect(screen.getByRole("tab", { name: /error-500/ })).toHaveAttribute("aria-selected", "true")
    await user.click(screen.getByRole("tab", { name: /created/ }))
    expect(await screen.findByText("Created")).toBeInTheDocument()
    expect(screen.getByText("1.5 s")).toBeInTheDocument()
    const headerBlock = screen.getByRole("region", { name: "Response headers of created" })
    expect(headerBlock).toHaveTextContent("X-Trace: abc")
    expect(headerBlock).toHaveTextContent("Location: /orders/1")
    expect(screen.getByRole("region", { name: "Body of created" }).textContent).toBe(
      JSON.stringify({ id: 1, ok: true }, null, 2),
    )
  })

  it("is live: a refresh after an edit shows the new state", async () => {
    const rule = shareRule("Limsa dashboard")
    const first = renderRoute(`/shared/${TOKEN}`)
    await screen.findByRole("heading", { level: 1, name: "Limsa dashboard" })
    first.unmount()

    rule.name = "Limsa dashboard v2"
    renderRoute(`/shared/${TOKEN}`)
    expect(await screen.findByRole("heading", { level: 1, name: "Limsa dashboard v2" })).toBeInTheDocument()
  })

  it("an unknown or revoked token shows the friendly page without the app shell (axe clean)", async () => {
    const { container } = renderRoute("/shared/nope")
    expect(await screen.findByRole("heading", { name: "This link isn't available" })).toBeInTheDocument()
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument()
    expect(screen.queryByText("Limsa dashboard")).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("a revoked link stops working", async () => {
    const rule = shareRule("Limsa dashboard")
    rule.shareToken = null
    renderRoute(`/shared/${TOKEN}`)
    expect(await screen.findByRole("heading", { name: "This link isn't available" })).toBeInTheDocument()
  })

  it("a server error is a retryable problem, not the not-found page, and never a sign-in redirect", async () => {
    const assign = vi.fn()
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign })
    server.use(
      http.get("*/api/v1/shared/rules/:token", () =>
        HttpResponse.json({ title: "Mockan couldn't load this", status: 500 }, { status: 500 }),
      ),
    )
    renderRoute(`/shared/${TOKEN}`)
    expect(await screen.findByRole("alert")).toHaveTextContent("Mockan couldn't load this")
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
    expect(assign).not.toHaveBeenCalled()
  })

  it("a 401 from a proxy in front is shown as an error, not a redirect to the login page", async () => {
    const assign = vi.fn()
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign })
    server.use(http.get("*/api/v1/shared/rules/:token", () => new HttpResponse(null, { status: 401 })))
    renderRoute(`/shared/${TOKEN}`)
    await screen.findByRole("alert")
    await waitFor(() => expect(assign).not.toHaveBeenCalled())
  })
})
