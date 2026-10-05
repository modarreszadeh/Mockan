import { describe, expect, it } from "vitest"

import type { MockRule } from "@/api/types"

import { ruleToCurl } from "./curl"

const rule = (over: Partial<MockRule>): MockRule =>
  ({
    method: "GET",
    matchType: "Exact",
    pattern: "/limsa/api/v1/dashboard",
    queryConditions: [],
    headerConditions: [],
    ...over,
  }) as MockRule

const BASE = "http://localhost:8090/ehtesham"

describe("ruleToCurl", () => {
  it("builds a plain GET through the gateway", () => {
    expect(ruleToCurl(rule({}), BASE)).toBe("curl -i 'http://localhost:8090/ehtesham/limsa/api/v1/dashboard'")
  })

  it("adds the method, query and header conditions", () => {
    const curl = ruleToCurl(
      rule({
        method: "POST",
        queryConditions: [
          { key: "force", operator: "exists" },
          { key: "q", operator: "equals", value: "a b" },
        ],
        headerConditions: [{ key: "X-Feature", operator: "equals", value: "it's beta" }],
      }),
      `${BASE}/`,
    )
    expect(curl).toBe(
      `curl -i -X POST -H 'X-Feature: it'\\''s beta' 'http://localhost:8090/ehtesham/limsa/api/v1/dashboard?force=1&q=a+b'`,
    )
  })

  it("fills Template parameters and treats ANY as GET", () => {
    expect(
      ruleToCurl(rule({ method: "ANY", matchType: "Template", pattern: "/orders/{id}/files/{*rest}" }), BASE),
    ).toBe("curl -i 'http://localhost:8090/ehtesham/orders/example/files/example'")
  })

  it("uses -I for HEAD and gives up on Regex", () => {
    expect(ruleToCurl(rule({ method: "HEAD" }), BASE)).toMatch(/^curl -I /)
    expect(ruleToCurl(rule({ matchType: "Regex", pattern: "^/a/\\d+$" }), BASE)).toBeNull()
  })
})
