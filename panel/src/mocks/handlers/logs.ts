/** `GET /me/request-logs` and "Mock this" (`POST /me/request-logs/{id}/create-rule`), PR-12 / FR-09. */
import { delay, http, HttpResponse } from "msw"

import { HTTP_METHODS, type MockRule, type RequestLogEntry } from "@/api/types"

import { db, persist } from "../db"
import { guard, newId, notFound, now, problem } from "../problem"
import { toResponse } from "./rules"

/** Never copied into a rule: framing, cookies and Mockan's own headers (admin-api.md "Mock this"). */
const SKIPPED_HEADERS = new Set(["content-type", "content-length", "transfer-encoding", "connection", "set-cookie"])

export const logHandlers = [
  http.get("*/api/v1/me/request-logs", async ({ request }) => {
    await delay()
    const stop = guard()
    if (stop) return stop
    const url = new URL(request.url)
    const source = url.searchParams.get("source")
    const path = url.searchParams.get("path")?.toLowerCase()
    const cursor = Number(url.searchParams.get("cursor") ?? Infinity)
    const limit = Math.min(Number(url.searchParams.get("limit") ?? 50), 200)
    const matching = db.logs
      .filter(
        (e) => e.id < cursor && (!source || e.source === source) && (!path || e.path.toLowerCase().includes(path)),
      )
      .sort((a, b) => b.id - a.id)
    const items = matching.slice(0, limit)
    return HttpResponse.json({
      items,
      nextCursor: matching.length > limit ? String(items[items.length - 1]!.id) : null,
    })
  }),

  http.post("*/api/v1/me/request-logs/:logId/create-rule", async ({ params }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const entry = db.logs.find((e) => String(e.id) === params.logId)
    if (!entry) return notFound("RequestLog")
    const id = newId()
    const contentType = entry.responseHeaders["content-type"] ?? "application/json"
    const headers = Object.fromEntries(
      Object.entries(entry.responseHeaders).filter(
        ([name, value]) =>
          !SKIPPED_HEADERS.has(name.toLowerCase()) && !name.toLowerCase().startsWith("x-mockan-") && value !== "***",
      ),
    )
    const rule: MockRule = {
      id,
      developerId: db.developer.id,
      serviceId: entry.serviceId,
      name: `${entry.method} ${entry.path}`,
      method: HTTP_METHODS.includes(entry.method as never) ? (entry.method as MockRule["method"]) : "ANY",
      matchType: "Exact",
      pattern: entry.path,
      queryConditions: [],
      headerConditions: [],
      priority: 100,
      isEnabled: true,
      activeResponseId: null,
      responses: [],
      createdAt: now(),
      updatedAt: now(),
    }
    const response = toResponse(
      id,
      {
        name: "from-log",
        statusCode: entry.statusCode,
        headers,
        contentType,
        body: entry.responseBodySample ?? "",
        delayMs: 0,
      },
      newId(),
    )
    if (!/^\/[^\s{}]*$/.test(entry.path))
      return problem(422, "validation_failed", "Some fields need attention", {
        errors: { pattern: ["This path can't be turned into an Exact rule."] },
      })
    rule.responses = [response]
    rule.activeResponseId = response.id
    db.rules.push(rule)
    persist()
    return HttpResponse.json(rule, { status: 201 })
  }),
]

/** One more entry, as the Gateway would log it (used by the simulated live feed and tests). */
export function appendLog(fields: Omit<RequestLogEntry, "id" | "developerId" | "timestamp">): RequestLogEntry {
  const entry: RequestLogEntry = {
    id: Math.max(0, ...db.logs.map((e) => e.id)) + 1,
    developerId: db.developer.id,
    timestamp: now(),
    ...fields,
  }
  db.logs.unshift(entry)
  persist()
  return entry
}
