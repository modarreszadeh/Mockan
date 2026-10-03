import { describe, expect, it } from "vitest"

import {
  delaySchema,
  jsonProblem,
  originProblem,
  patternProblem,
  responseFormSchema,
  ruleFormSchema,
  slugProblem,
  statusCodeSchema,
} from "./validation"

describe("PR-01 DeveloperSlug", () => {
  it.each(["ehtesham", "qoolak", "a1", "front-end-2", "a".repeat(32)])("accepts %s", (slug) => {
    expect(slugProblem(slug)).toBeNull()
  })

  it.each([
    ["", "Enter a slug."],
    ["a", "at least 2"],
    ["a".repeat(33), "at most 32"],
    ["Ehtesham", "lowercase"],
    ["1dev", "Start with a lowercase letter"],
    ["dev_1", "only lowercase letters, digits and hyphens"],
    ["_mockan", "reserved"],
    ["api", "reserved"],
    ["hubs", "reserved"],
    ["health", "reserved"],
  ])("rejects %j", (slug, reason) => {
    expect(slugProblem(slug)).toContain(reason)
  })
})

describe("PR-05 patterns", () => {
  it("Exact/Template/Prefix patterns must start with /", () => {
    for (const type of ["Exact", "Template", "Prefix"] as const)
      expect(patternProblem(type, "limsa/api")).toMatch(/Start the pattern/)
  })

  it("accepts the dashboard Exact pattern", () => {
    expect(patternProblem("Exact", "/limsa/api/v1/dashboard")).toBeNull()
  })

  it("template accepts {id} and a trailing {*rest}", () => {
    expect(patternProblem("Template", "/limsa/api/v1/orders/{id}")).toBeNull()
    expect(patternProblem("Template", "/files/{*rest}")).toBeNull()
  })

  it("PR-05 template pattern rejects {*rest} in the middle", () => {
    expect(patternProblem("Template", "/files/{*rest}/meta")).toMatch(/last segment/)
  })

  it("template rejects partial-segment params and duplicates", () => {
    expect(patternProblem("Template", "/orders/id-{id}")).toMatch(/whole segment/)
    expect(patternProblem("Template", "/a/{id}/b/{id}")).toMatch(/twice/)
  })

  it("Exact rejects braces", () => {
    expect(patternProblem("Exact", "/orders/{id}")).toMatch(/Use Template/)
  })

  it("regex is bounded to 512 characters (D-17)", () => {
    expect(patternProblem("Regex", `^/${"a".repeat(511)}`)).toMatch(/at most 512/)
    expect(patternProblem("Regex", "^/limsa/api/v1/(items|goods)/\\d+$")).toBeNull()
  })

  it("regex rejects what RE2 can't compile", () => {
    expect(patternProblem("Regex", "^/(?=a)")).toMatch(/lookahead/)
    expect(patternProblem("Regex", "^/(a)\\1")).toMatch(/backreferences/)
    expect(patternProblem("Regex", "^/(unclosed")).toMatch(/Invalid regex/)
  })
})

describe("PR-06 response", () => {
  it("status code range is 100–599", () => {
    expect(statusCodeSchema.safeParse(99).success).toBe(false)
    expect(statusCodeSchema.safeParse(100).success).toBe(true)
    expect(statusCodeSchema.safeParse(599).success).toBe(true)
    expect(statusCodeSchema.safeParse(600).success).toBe(false)
    expect(statusCodeSchema.safeParse(200.5).success).toBe(false)
  })

  it("delay range is 0–30000 ms", () => {
    expect(delaySchema.safeParse(-1).success).toBe(false)
    expect(delaySchema.safeParse(0).success).toBe(true)
    expect(delaySchema.safeParse(30_000).success).toBe(true)
    expect(delaySchema.safeParse(30_001).success).toBe(false)
  })

  it("PR-06 invalid JSON reports line and column", () => {
    expect(jsonProblem('{\n  "a": 1,\n}')).toMatchObject({ line: 3, column: 1 })
    expect(jsonProblem('{"a": [1, 2]}')).toBeNull()
  })

  it("JSON check only applies to JSON content types; body max 1 MB", () => {
    const base = { name: "success", statusCode: 200, headers: [], delayMs: 0 }
    expect(responseFormSchema.safeParse({ ...base, contentType: "text/plain", body: "{oops" }).success).toBe(true)
    expect(responseFormSchema.safeParse({ ...base, contentType: "application/json", body: "{oops" }).success).toBe(
      false,
    )
    expect(responseFormSchema.safeParse({ ...base, contentType: "application/problem+json", body: "{}" }).success).toBe(
      true,
    )
    expect(
      responseFormSchema.safeParse({ ...base, contentType: "text/plain", body: "x".repeat(1024 * 1024 + 1) }).success,
    ).toBe(false)
  })

  it("rule form puts pattern errors on the pattern field", () => {
    const result = ruleFormSchema.safeParse({
      name: "x",
      method: "GET",
      matchType: "Exact",
      pattern: "nope",
      serviceId: "",
      priority: 100,
      queryConditions: [],
      headerConditions: [],
      response: {
        name: "success",
        statusCode: 200,
        contentType: "application/json",
        headers: [],
        body: "",
        delayMs: 0,
      },
    })
    expect(result.success).toBe(false)
    expect(result.error?.issues[0]?.path).toEqual(["pattern"])
  })
})

describe("PR-03 allowed origins", () => {
  it.each(["http://localhost:*", "http://127.0.0.1:5173", "https://*.novin.local"])("accepts %s", (o) =>
    expect(originProblem(o)).toBeNull(),
  )
  it.each(["localhost:3000", "http://localhost:3000/app", "http://local host"])("rejects %s", (o) =>
    expect(originProblem(o)).not.toBeNull(),
  )
})
