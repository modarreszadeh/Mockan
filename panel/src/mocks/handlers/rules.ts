/**
 * `/me/rules*` (arch §10). Validation errors use FastAPI's default 422 shape (TODO(OQ-F1)) so the Panel
 * exercises both field-error formats. Payload shapes: TODO(OQ-F5).
 */
import { delay, http, HttpResponse } from "msw"

import {
  HTTP_METHODS,
  MATCH_TYPES,
  type MockResponse,
  type MockResponseInput,
  type MockRule,
  type MockRuleCreate,
  type MockRuleUpdate,
} from "@/api/types"
import { byteLength, MAX_BODY_BYTES, MAX_DELAY_MS, patternProblem } from "@/lib/validation"

import { db, persist } from "../db"
import { fastApi422, guard, newId, notFound, now, problem } from "../problem"

export type Issue = { loc: (string | number)[]; msg: string }

export function validateRule(input: MockRuleUpdate): Issue[] {
  const issues: Issue[] = []
  if (!input.name?.trim()) issues.push({ loc: ["name"], msg: "Name the rule." })
  if (!HTTP_METHODS.includes(input.method)) issues.push({ loc: ["method"], msg: "Unknown method." })
  if (!MATCH_TYPES.includes(input.matchType)) issues.push({ loc: ["match_type"], msg: "Unknown match type." })
  else {
    // The real server compiles Regex patterns with RE2 (D-17); this mirrors its rejections.
    const issue = patternProblem(input.matchType, input.pattern ?? "")
    if (issue) issues.push({ loc: ["pattern"], msg: issue })
  }
  if (input.serviceId !== null && !db.services.some((s) => s.id === input.serviceId))
    issues.push({ loc: ["service_id"], msg: "Unknown Service." })
  if (!Number.isInteger(input.priority) || input.priority < 0)
    issues.push({ loc: ["priority"], msg: "Priority must be a whole number of 0 or more." })
  return issues
}

export function validateResponse(input: MockResponseInput, prefix: (string | number)[] = []): Issue[] {
  const issues: Issue[] = []
  const at = (field: string) => [...prefix, field]
  if (!input.name?.trim()) issues.push({ loc: at("name"), msg: "Name the scenario." })
  if (!Number.isInteger(input.statusCode) || input.statusCode < 100 || input.statusCode > 599)
    issues.push({ loc: at("status_code"), msg: "Status code must be between 100 and 599." })
  if (!Number.isInteger(input.delayMs) || input.delayMs < 0 || input.delayMs > MAX_DELAY_MS)
    issues.push({ loc: at("delay_ms"), msg: "Delay must be between 0 and 30000 ms." })
  if (byteLength(input.body ?? "") > MAX_BODY_BYTES) issues.push({ loc: at("body"), msg: "Body must be at most 1 MB." })
  return issues
}

export const toResponse = (ruleId: string, input: MockResponseInput, id: string = newId()): MockResponse => ({
  id,
  ruleId,
  name: input.name.trim(),
  statusCode: input.statusCode,
  headers: input.headers ?? {},
  contentType: input.contentType || "application/json",
  body: input.body ?? "",
  bodyMode: input.bodyMode ?? "Static",
  delayMs: input.delayMs ?? 0,
  createdAt: now(),
  updatedAt: now(),
})

export const ruleFields = (input: MockRuleUpdate) => ({
  serviceId: input.serviceId,
  name: input.name.trim(),
  method: input.method,
  matchType: input.matchType,
  pattern: input.pattern,
  queryConditions: input.queryConditions ?? [],
  headerConditions: input.headerConditions ?? [],
  priority: input.priority,
})

const findRule = (id: unknown) => db.rules.find((r) => r.id === id)

export const ruleHandlers = [
  http.get("*/api/v1/me/rules", async () => {
    await delay()
    return guard() ?? HttpResponse.json(db.rules)
  }),

  http.post("*/api/v1/me/rules/toggle-all", async ({ request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const { isEnabled } = (await request.json()) as { isEnabled: boolean }
    let updated = 0
    db.rules = db.rules.map((rule) => {
      if (rule.isEnabled === isEnabled) return rule
      updated += 1
      return { ...rule, isEnabled, updatedAt: now() }
    })
    persist()
    return HttpResponse.json({ updated })
  }),

  http.post("*/api/v1/me/rules", async ({ request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const input = (await request.json()) as MockRuleCreate
    const issues = [
      ...validateRule(input),
      ...(input.responses?.length ? [] : [{ loc: ["responses"], msg: "Add at least one response." }]),
      ...(input.responses ?? []).flatMap((r, i) => validateResponse(r, ["responses", i])),
    ]
    if (issues.length) return fastApi422(issues)
    const id = newId()
    const responses = input.responses.map((r) => toResponse(id, r))
    const rule: MockRule = {
      id,
      developerId: db.developer.id,
      ...ruleFields(input),
      isEnabled: input.isEnabled ?? true,
      activeResponseId: responses[0]?.id ?? null,
      responses,
      createdAt: now(),
      updatedAt: now(),
    }
    db.rules.push(rule)
    persist()
    return HttpResponse.json(rule, { status: 201 })
  }),

  http.get("*/api/v1/me/rules/:ruleId", async ({ params }) => {
    await delay()
    const stop = guard()
    if (stop) return stop
    const rule = findRule(params.ruleId)
    return rule ? HttpResponse.json(rule) : notFound("MockRule")
  }),

  http.put("*/api/v1/me/rules/:ruleId", async ({ params, request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    if (!rule) return notFound("MockRule")
    const input = (await request.json()) as MockRuleUpdate
    const issues = validateRule(input)
    if (issues.length) return fastApi422(issues)
    Object.assign(rule, ruleFields(input), input.isEnabled !== undefined ? { isEnabled: input.isEnabled } : {}, {
      updatedAt: now(),
    })
    persist()
    return HttpResponse.json(rule)
  }),

  http.delete("*/api/v1/me/rules/:ruleId", async ({ params }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    if (!findRule(params.ruleId)) return notFound("MockRule")
    db.rules = db.rules.filter((r) => r.id !== params.ruleId)
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.post("*/api/v1/me/rules/:ruleId/toggle", async ({ params, request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    if (!rule) return notFound("MockRule")
    const { isEnabled } = (await request.json()) as { isEnabled: boolean }
    Object.assign(rule, { isEnabled, updatedAt: now() })
    persist()
    return HttpResponse.json(rule)
  }),

  http.post("*/api/v1/me/rules/:ruleId/responses", async ({ params, request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    if (!rule) return notFound("MockRule")
    const input = (await request.json()) as MockResponseInput
    const issues = validateResponse(input)
    if (issues.length) return fastApi422(issues)
    const response = toResponse(rule.id, input)
    rule.responses.push(response)
    rule.activeResponseId ??= response.id
    rule.updatedAt = now()
    persist()
    return HttpResponse.json(response, { status: 201 })
  }),

  http.put("*/api/v1/me/rules/:ruleId/responses/:responseId", async ({ params, request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    const index = rule?.responses.findIndex((r) => r.id === params.responseId) ?? -1
    if (!rule || index < 0) return notFound("MockResponse")
    const input = (await request.json()) as MockResponseInput
    const issues = validateResponse(input)
    if (issues.length) return fastApi422(issues)
    const updated = {
      ...toResponse(rule.id, input, rule.responses[index]!.id),
      createdAt: rule.responses[index]!.createdAt,
    }
    rule.responses[index] = updated
    rule.updatedAt = now()
    persist()
    return HttpResponse.json(updated)
  }),

  http.delete("*/api/v1/me/rules/:ruleId/responses/:responseId", async ({ params }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    if (!rule?.responses.some((r) => r.id === params.responseId)) return notFound("MockResponse")
    // Like the real API (G-3): a rule always keeps an active response.
    if (rule.responses.length === 1)
      return problem(409, "last_response", "A rule needs at least one response", {
        detail: "Add another response first, or delete the rule.",
      })
    rule.responses = rule.responses.filter((r) => r.id !== params.responseId)
    if (rule.activeResponseId === params.responseId) rule.activeResponseId = rule.responses[0]!.id
    rule.updatedAt = now()
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.post("*/api/v1/me/rules/:ruleId/responses/:responseId/activate", async ({ params }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const rule = findRule(params.ruleId)
    if (!rule?.responses.some((r) => r.id === params.responseId)) return notFound("MockResponse")
    rule.activeResponseId = params.responseId as string
    rule.updatedAt = now()
    persist()
    return HttpResponse.json(rule)
  }),
]
