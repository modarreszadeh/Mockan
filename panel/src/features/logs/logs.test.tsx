import { act, screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { hubUrl } from "@/api/queries/logs"
import type { RequestLogEntry } from "@/api/types"
import { db, resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"
import { installFakeSocket } from "@/test/fake-socket"
import { axe, renderRoute } from "@/test/render"

let socket: ReturnType<typeof installFakeSocket>
beforeEach(() => {
  socket = installFakeSocket()
})
afterEach(() => vi.unstubAllGlobals())

const liveEntry = (over: Partial<RequestLogEntry> = {}): RequestLogEntry => ({
  id: 99,
  developerId: db.developer.id,
  timestamp: new Date().toISOString(),
  method: "GET",
  path: "/limsa/api/v1/live-one",
  query: "",
  serviceId: null,
  source: "Proxied",
  ruleId: null,
  statusCode: 200,
  durationMs: 12,
  requestHeaders: {},
  responseHeaders: {},
  requestBodySample: null,
  responseBodySample: null,
  ...over,
})

describe("SCR-09 Live log", () => {
  it("PR-12 lists recent requests, newest first (axe clean)", async () => {
    const { container } = renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    const paths = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("button")[0]!.textContent)
    expect(paths[0]).toBe("/limsa/api/v1/dashboard")
    expect(paths).toHaveLength(8)
    expect(await axe(container)).toHaveNoViolations()
  })

  it("connects to the hub at the Admin root and shows Live once open", async () => {
    renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    expect(socket.current?.url).toBe(hubUrl())
    expect(socket.current?.url).toMatch(/^wss?:\/\/[^/]+\/hubs\/request-log$/)
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Connecting…")
    act(() => socket.current!.open())
    expect(screen.getByText("Live")).toBeInTheDocument()
  })

  it("PR-12 a live entry appears at the top without a reload", async () => {
    renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    act(() => {
      socket.current!.open()
      socket.current!.send(liveEntry())
    })
    const first = screen.getAllByRole("row")[1]!
    expect(within(first).getByText("/limsa/api/v1/live-one")).toBeInTheDocument()
  })

  it("a live entry that the filters exclude isn't shown", async () => {
    renderRoute("/logs?source=Error")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/orders" })
    act(() => socket.current!.send(liveEntry({ source: "Proxied" })))
    expect(screen.queryByText("/limsa/api/v1/live-one")).not.toBeInTheDocument()
    act(() => socket.current!.send(liveEntry({ id: 100, source: "Error", path: "/limsa/api/v1/live-two" })))
    expect(screen.getByText("/limsa/api/v1/live-two")).toBeInTheDocument()
  })

  it("Pause holds new entries back until Resume", async () => {
    const { user } = renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    await user.click(screen.getByRole("button", { name: "Pause" }))
    act(() => socket.current!.send(liveEntry()))
    expect(screen.queryByText("/limsa/api/v1/live-one")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Resume (1 new)" }))
    expect(screen.getByText("/limsa/api/v1/live-one")).toBeInTheDocument()
  })

  it("reconnects after the connection drops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderRoute("/logs")
      await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
      act(() => socket.current!.open())
      act(() => socket.current!.drop())
      expect(screen.getByText("Reconnecting…")).toBeInTheDocument()
      expect(socket.all()).toHaveLength(1)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_100)
      })
      expect(socket.all()).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it("filters by source through the API and keeps it in the URL", async () => {
    const { user, router } = renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    await user.click(screen.getByRole("combobox", { name: "Source" }))
    await user.click(await screen.findByRole("option", { name: "Error" }))
    expect(router.state.location.search).toBe("?source=Error")
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(2))
    expect(screen.getByText("502")).toBeInTheDocument()
  })

  it("filters by path text", async () => {
    const { user } = renderRoute("/logs")
    await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" })
    await user.type(screen.getByRole("searchbox", { name: "Filter by path" }), "identity")
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(2))
    expect(screen.getByText("/identity/connect/token")).toBeInTheDocument()
  })

  it("NFR-07 the drawer shows masked headers and bodies exactly as received", async () => {
    const { user } = renderRoute("/logs")
    await user.click(await screen.findByRole("button", { name: "Details of POST /identity/connect/token" }))
    const drawer = await screen.findByRole("dialog")
    const headers = within(drawer).getByRole("region", { name: "Request headers" })
    expect(headers).toHaveTextContent("authorization: ***")
    expect(within(drawer).getByRole("region", { name: "Request body sample" })).toHaveTextContent('"password": "***"')
    expect(within(drawer).getByText("identity")).toBeInTheDocument()
  })

  it("FR-09 Mock this creates an Exact rule and opens it", async () => {
    const { user, router } = renderRoute("/logs")
    await user.click(await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/orders/4211" }))
    await user.click(await screen.findByRole("button", { name: "Mock this" }))
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/rules\/.+/))
    const rule = db.rules.at(-1)!
    expect(rule).toMatchObject({ matchType: "Exact", pattern: "/limsa/api/v1/orders/4211", method: "GET" })
    expect(rule.responses[0]).toMatchObject({ statusCode: 200 })
  })

  it("FR-09 a Mocked entry offers the rule that answered it, not a second rule", async () => {
    const { user, router } = renderRoute("/logs")
    await user.click(await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/dashboard" }))
    const drawer = await screen.findByRole("dialog")
    expect(within(drawer).queryByRole("button", { name: "Mock this" })).not.toBeInTheDocument()
    await user.click(within(drawer).getByRole("link", { name: "Open the rule" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/rules/0192f5a0-0000-7000-8000-0000000a0001"))
  })

  it("FR-09 Mock this is offered for an Error entry", async () => {
    const { user } = renderRoute("/logs")
    await user.click(await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/orders" }))
    expect(await within(await screen.findByRole("dialog")).findByRole("button", { name: "Mock this" })).toBeInTheDocument()
  })

  it("FR-09 Mock this explains a refusal", async () => {
    server.use(
      http.post("*/api/v1/me/request-logs/:id/create-rule", () =>
        HttpResponse.json(
          {
            title: "Some fields need attention",
            status: 422,
            code: "validation_failed",
            errors: { "responses.0.body": ["The response body was cut at 16 KB; mock it by hand."] },
          },
          { status: 422 },
        ),
      ),
    )
    const { user, router } = renderRoute("/logs")
    await user.click(await screen.findByRole("button", { name: "Details of GET /limsa/api/v1/orders/4211" }))
    await user.click(await screen.findByRole("button", { name: "Mock this" }))
    expect(await screen.findByText("The response body was cut at 16 KB; mock it by hand.")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/logs")
  })

  it("shows the empty state with the base URL when nothing was logged", async () => {
    resetDb("empty")
    renderRoute("/logs")
    expect(await screen.findByText("No requests yet")).toBeInTheDocument()
    expect(screen.getByText(/mock\.novin-tools\.com\/ehtesham/)).toBeInTheDocument()
  })

  it("shows a retryable error when the history can't be loaded", async () => {
    resetDb("broken")
    renderRoute("/logs")
    expect(await screen.findByRole("alert")).toHaveTextContent("Mockan couldn't load this")
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
  })

  it("pages older requests with a cursor", async () => {
    const base = db.logs[0]!
    db.logs = Array.from({ length: 60 }, (_, i) => ({ ...base, id: 100 - i, path: `/limsa/page/${100 - i}` }))
    const { user } = renderRoute("/logs")
    await screen.findByText("/limsa/page/100")
    expect(screen.getAllByRole("row")).toHaveLength(51)
    await user.click(screen.getByRole("button", { name: "Load older requests" }))
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(61))
    expect(screen.queryByRole("button", { name: "Load older requests" })).not.toBeInTheDocument()
  })
})
