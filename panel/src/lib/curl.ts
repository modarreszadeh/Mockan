import type { MockRule } from "@/api/types"

const shellQuote = (value: string) => `'${value.replace(/'/g, `'\\''`)}'`

/** A concrete path the rule matches, or `null` when there isn't an obvious one (a Regex pattern). */
export function samplePath(rule: Pick<MockRule, "matchType" | "pattern">): string | null {
  switch (rule.matchType) {
    case "Exact":
    case "Prefix":
      return rule.pattern
    case "Template":
      return rule.pattern.replace(/\{\*?\w+\}/g, "example")
    case "Regex":
      return null
  }
}

/**
 * A `curl` command that sends a request this rule matches through the Gateway (`gatewayBase` = public URL + slug),
 * including the rule's method, query and header conditions. `null` when no sample path can be derived.
 */
export function ruleToCurl(rule: MockRule, gatewayBase: string): string | null {
  const path = samplePath(rule)
  if (path === null) return null

  const query = new URLSearchParams()
  for (const c of rule.queryConditions) query.append(c.key, c.operator === "exists" ? "1" : (c.value ?? ""))
  const url = `${gatewayBase.replace(/\/+$/, "")}${path}${query.size > 0 ? `?${query}` : ""}`

  const parts = ["curl", "-i"]
  if (rule.method === "HEAD") parts[1] = "-I"
  else if (rule.method !== "ANY" && rule.method !== "GET") parts.push("-X", rule.method)
  for (const c of rule.headerConditions)
    parts.push("-H", shellQuote(`${c.key}: ${c.operator === "exists" ? "1" : (c.value ?? "")}`))
  parts.push(shellQuote(url))
  return parts.join(" ")
}
