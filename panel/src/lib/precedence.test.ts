import { describe, expect, it } from "vitest"

import { sortByPrecedence } from "./precedence"

const rule = (
  name: string,
  priority: number,
  matchType: "Exact" | "Template" | "Prefix" | "Regex",
  pattern: string,
  createdAt: string,
) => ({
  name,
  priority,
  matchType,
  pattern,
  createdAt,
})

describe("PR-05 precedence (arch §7.2)", () => {
  it("orders by priority, match type, longer pattern, then older rule", () => {
    const rules = [
      rule("regex", 100, "Regex", "^/a", "2026-01-01T00:00:00Z"),
      rule("prefix", 100, "Prefix", "/a/", "2026-01-01T00:00:00Z"),
      rule("exact-short", 100, "Exact", "/a", "2026-01-01T00:00:00Z"),
      rule("exact-long", 100, "Exact", "/a/b", "2026-01-01T00:00:00Z"),
      rule("template-newer", 100, "Template", "/a/{x}", "2026-02-01T00:00:00Z"),
      rule("template-older", 100, "Template", "/a/{y}", "2026-01-01T00:00:00Z"),
      rule("priority-10", 10, "Regex", ".*", "2026-03-01T00:00:00Z"),
    ]
    expect(sortByPrecedence(rules).map((r) => r.name)).toEqual([
      "priority-10",
      "exact-long",
      "exact-short",
      "template-older",
      "template-newer",
      "prefix",
      "regex",
    ])
  })
})
