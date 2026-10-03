import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"

import { server } from "@/mocks/server"

import { api, ApiError, extractFieldErrors, LOGIN_URL } from "./client"

describe("api client", () => {
  it("TODO(OQ-F1) maps problem+json errors and FastAPI 422 detail[] to camelCase fields", () => {
    expect(extractFieldErrors({ errors: { path_prefix: ["taken"], name: ["dup"] } })).toEqual({
      pathPrefix: ["taken"],
      name: ["dup"],
    })
    expect(
      extractFieldErrors({
        detail: [
          { loc: ["body", "responses", 0, "status_code"], msg: "bad" },
          { loc: ["body", "pattern"], msg: "nope" },
        ],
      } as never),
    ).toEqual({ "responses.0.statusCode": ["bad"], pattern: ["nope"] })
  })

  it("throws ApiError with the parsed problem on non-2xx", async () => {
    server.use(
      http.get("*/api/v1/boom", () =>
        HttpResponse.json({ title: "Nope", detail: "Broken", code: "internal_error" }, { status: 500 }),
      ),
    )
    const error = await api.get("/boom").catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe("internal_error")
    expect((error as ApiError).message).toBe("Broken")
  })

  it("redirects the browser to SSO login on 401 (full navigation)", async () => {
    const assign = vi.fn()
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign, origin: "http://localhost:3000" })
    server.use(http.get("*/api/v1/me", () => new HttpResponse(null, { status: 401 })))
    await expect(api.get("/me")).rejects.toBeInstanceOf(ApiError)
    expect(assign).toHaveBeenCalledWith(LOGIN_URL)
  })
})
