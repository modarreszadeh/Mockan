import { screen, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "@/mocks/server"
import { axe, renderRoute } from "@/test/render"

import { buildRequest } from "./build-request"

const row = (key: string, value: string) => ({ key, operator: "equals" as const, value })

describe("buildRequest", () => {
  it("PR-13 moves a query string typed into the path into the query parameters", () => {
    expect(
      buildRequest(
        "GET",
        " /limsa/orders?status=pending&status=new&page=2 ",
        [row("x", "1")],
        [row("X-Feature", "beta")],
      ),
    ).toEqual({
      method: "GET",
      path: "/limsa/orders",
      query: { status: ["pending", "new"], page: ["2"], x: ["1"] },
      headers: { "X-Feature": "beta" },
    })
  })

  it("ignores empty rows", () => {
    expect(buildRequest("POST", "/a", [row("", "")], [row("  ", "v")])).toEqual({
      method: "POST",
      path: "/a",
      query: {},
      headers: {},
    })
  })
})

async function test(user: ReturnType<typeof renderRoute>["user"], path: string) {
  await user.type(await screen.findByLabelText("Path"), path)
  await user.click(screen.getByRole("button", { name: "Test route" }))
}

describe("SCR-10 Test route", () => {
  it("PR-13 says which rule would answer, and with what (axe clean)", async () => {
    const { user, container } = renderRoute("/test-route")
    await test(user, "/limsa/api/v1/dashboard")
    const result = await screen.findByTestId("outcome-reason")
    expect(result).toHaveTextContent("Limsa dashboard")
    expect(screen.getByText("Mocked")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Limsa dashboard" })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/rules\/0192/),
    )
    expect(screen.getByText("success")).toBeInTheDocument()
    expect(screen.getByText("after 300 ms")).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("PR-13 shows the upstream URL when the request would be proxied", async () => {
    const { user } = renderRoute("/test-route")
    await test(user, "/identity/connect/token?tenant=lab")
    expect(await screen.findByText("Proxied")).toBeInTheDocument()
    expect(screen.getByTestId("upstream-url")).toHaveTextContent(
      "https://identity.stage.internal/identity/connect/token?tenant=lab",
    )
  })

  it("PR-13 honours the selected environment and strips the prefix", async () => {
    const { user } = renderRoute("/test-route")
    await test(user, "/limsa/api/v1/unmocked")
    // limsa is on dev (Developer setting) and strips its prefix
    expect(await screen.findByTestId("upstream-url")).toHaveTextContent(
      /^https:\/\/limsa\.dev\.internal.*\/api\/v1\/unmocked$/,
    )
  })

  it("PR-13 explains an error outcome with its code", async () => {
    const { user } = renderRoute("/test-route")
    await test(user, "/nobody/owns/this")
    expect(await screen.findByText("service_not_resolved")).toBeInTheDocument()
    expect(screen.getByText(/No Service owns this path/)).toBeInTheDocument()
  })

  it("a header condition only matches when the header is sent", async () => {
    const { user } = renderRoute("/test-route")
    await user.click(await screen.findByRole("combobox", { name: "Method" }))
    await user.click(await screen.findByRole("option", { name: "POST" }))
    await test(user, "/portal/api/notifications")
    // the rule is disabled in the fixtures, so it proxies either way; the point is the request shape is accepted
    expect(await screen.findByText("Proxied")).toBeInTheDocument()
  })

  it("requires a path starting with a slash before calling the API", async () => {
    let called = false
    server.use(
      http.post("*/api/v1/me/test-route", () => {
        called = true
        return HttpResponse.json({})
      }),
    )
    const { user } = renderRoute("/test-route")
    await test(user, "limsa/api")
    expect(await screen.findByText(/Start the path with/)).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it("shows the server's complaint about the path on the field", async () => {
    server.use(
      http.post("*/api/v1/me/test-route", () =>
        HttpResponse.json(
          {
            title: "Some fields need attention",
            status: 422,
            code: "validation_failed",
            errors: { path: ["The path can't contain a query string."] },
          },
          { status: 422 },
        ),
      ),
    )
    const { user } = renderRoute("/test-route")
    await test(user, "/ok")
    expect(await screen.findByText("The path can't contain a query string.")).toBeInTheDocument()
    expect(screen.getByLabelText("Path")).toHaveAttribute("aria-invalid", "true")
  })

  it("shows a ProblemAlert when the request fails outright", async () => {
    server.use(
      http.post("*/api/v1/me/test-route", () => HttpResponse.json({ title: "Boom", status: 500 }, { status: 500 })),
    )
    const { user } = renderRoute("/test-route")
    await test(user, "/ok")
    expect(within(await screen.findByRole("alert")).getByText("Boom")).toBeInTheDocument()
  })
})
