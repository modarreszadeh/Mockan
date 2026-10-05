/**
 * A small stand-in for the Gateway's decision (`POST /me/test-route`) so the MSW backend can answer it:
 * the first enabled rule in precedence order that matches, else the Service that owns the path, else an error.
 * The real server runs the Gateway's own code (PR-13); this only has to be believable.
 */
import type { Condition, MockRule, Service, TestRouteRequest, TestRouteResult } from "@/api/types"
import { sortByPrecedence } from "@/lib/precedence"

import type { MockDb } from "./db"
import { selectedEnvironment } from "@/api/queries/services"

const trimSlash = (path: string) => (path.length > 1 ? path.replace(/\/+$/, "") : path)

function matchesPattern(rule: MockRule, path: string): boolean {
  switch (rule.matchType) {
    case "Exact":
      return trimSlash(path).toLowerCase() === trimSlash(rule.pattern).toLowerCase()
    case "Prefix":
      return path.toLowerCase().startsWith(rule.pattern.toLowerCase())
    case "Template": {
      const source = rule.pattern
        .split("/")
        .map((segment) =>
          /^\{\*\w+\}$/.test(segment)
            ? ".*"
            : /^\{\w+\}$/.test(segment)
              ? "[^/]+"
              : segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
        )
        .join("/")
      return new RegExp(`^${source}/?$`, "i").test(path)
    }
    case "Regex":
      try {
        return new RegExp(rule.pattern).test(path)
      } catch {
        return false
      }
  }
}

function conditionHolds(condition: Condition, values: string[] | undefined) {
  if (!values) return false
  return condition.operator === "exists" || values.includes(condition.value ?? "")
}

export function decideRoute(db: MockDb, request: TestRouteRequest): TestRouteResult {
  if (!db.developer.slug || !db.developer.isEnabled)
    return { outcome: "error", reason: "You have no active workspace.", errorCode: "developer_not_found" }

  const method = (request.method ?? "GET").toUpperCase()
  const query = request.query ?? {}
  const headers = Object.fromEntries(Object.entries(request.headers ?? {}).map(([k, v]) => [k.toLowerCase(), [v]]))

  const rule = sortByPrecedence(db.rules.filter((r) => r.isEnabled)).find(
    (r) =>
      (r.method === "ANY" || r.method === method) &&
      matchesPattern(r, request.path) &&
      r.queryConditions.every((c) => conditionHolds(c, query[c.key])) &&
      r.headerConditions.every((c) => conditionHolds(c, headers[c.key.toLowerCase()])),
  )
  if (rule) {
    const active = rule.responses.find((r) => r.id === rule.activeResponseId) ?? rule.responses[0]!
    return {
      outcome: "mock",
      reason: `${rule.matchType} rule “${rule.name}” (${rule.pattern}) won with priority ${rule.priority}`,
      rule: {
        id: rule.id,
        name: rule.name,
        method: rule.method,
        matchType: rule.matchType,
        pattern: rule.pattern,
        priority: rule.priority,
        activeResponse: {
          id: active.id,
          name: active.name,
          statusCode: active.statusCode,
          delayMs: active.delayMs,
        },
      },
    }
  }

  const service: Service | undefined = [...db.services]
    .sort((a, b) => b.pathPrefix.length - a.pathPrefix.length)
    .find((s) => request.path === s.pathPrefix || request.path.startsWith(`${s.pathPrefix}/`))
  const environment = service && selectedEnvironment(service, db.serviceSettings)
  if (!service || !environment)
    return {
      outcome: "error",
      reason: "No rule matches and no Service owns this path.",
      errorCode: "service_not_resolved",
    }
  const forwarded = service.stripPrefix ? request.path.slice(service.pathPrefix.length) || "/" : request.path
  const search = new URLSearchParams(
    Object.entries(query).flatMap(([k, vs]) => vs.map((v) => [k, v] as [string, string])),
  )
  return {
    outcome: "proxy",
    reason: `No enabled rule matches; Service “${service.name}” (${service.pathPrefix}) forwards to its ${environment.environment} environment.`,
    service: { id: service.id, name: service.name, environment: environment.environment },
    upstreamUrl: `${environment.baseUrl.replace(/\/+$/, "")}${forwarded}${search.size ? `?${search}` : ""}`,
  }
}
