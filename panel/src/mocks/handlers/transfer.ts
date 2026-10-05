/** `GET /me/rules/export` and `POST /me/rules/import` (FR-12, PR-14): validated as a whole, written all or nothing. */
import { delay, http, HttpResponse } from "msw"

import type { ExportedRule, ImportMode, MockRule, RulesExport } from "@/api/types"

import { db, persist } from "../db"
import { guard, newId, now, problem } from "../problem"
import { ruleFields, toResponse, validateResponse, validateRule } from "./rules"

const snakeToCamel = (s: string) => s.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())

export const transferHandlers = [
  http.get("*/api/v1/me/rules/export", async () => {
    await delay()
    const stop = guard()
    if (stop) return stop
    const rules: ExportedRule[] = db.rules.map((rule) => ({
      name: rule.name,
      method: rule.method,
      matchType: rule.matchType,
      pattern: rule.pattern,
      queryConditions: rule.queryConditions,
      headerConditions: rule.headerConditions,
      priority: rule.priority,
      isEnabled: rule.isEnabled,
      serviceName: db.services.find((s) => s.id === rule.serviceId)?.name ?? null,
      activeResponse: Math.max(
        0,
        rule.responses.findIndex((r) => r.id === rule.activeResponseId),
      ),
      responses: rule.responses.map(({ name, statusCode, headers, contentType, body, bodyMode, delayMs }) => ({
        name,
        statusCode,
        headers,
        contentType,
        body,
        bodyMode,
        delayMs,
      })),
    }))
    return HttpResponse.json({ version: 1, rules } satisfies RulesExport)
  }),

  http.post("*/api/v1/me/rules/import", async ({ request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const mode: ImportMode = new URL(request.url).searchParams.get("mode") === "replace" ? "replace" : "merge"
    const file = (await request.json()) as { version?: number; rules?: ExportedRule[] }
    if (file.version !== 1 || !Array.isArray(file.rules))
      return problem(422, "validation_failed", "Some fields need attention", {
        errors: { version: ["Only version 1 files can be imported."] },
      })

    // Every problem at once, keyed `rules.<i>.<field>` / `rules.<i>.responses.<j>.<field>` (G-1).
    const errors: Record<string, string[]> = {}
    const add = (loc: (string | number)[], msg: string) => {
      const key = loc.map((p) => (typeof p === "number" ? String(p) : snakeToCamel(p))).join(".")
      ;(errors[key] ??= []).push(msg)
    }
    file.rules.forEach((rule, i) => {
      const serviceId = rule.serviceName ? db.services.find((s) => s.name === rule.serviceName)?.id : null
      if (rule.serviceName && !serviceId) add(["rules", i, "serviceName"], `Unknown Service “${rule.serviceName}”.`)
      for (const issue of validateRule({ ...rule, serviceId: serviceId ?? null, method: rule.method as never }))
        add(["rules", i, ...issue.loc], issue.msg)
      if (!rule.responses?.length) add(["rules", i, "responses"], "Add at least one response.")
      rule.responses?.forEach((response, j) => {
        for (const issue of validateResponse(response, ["rules", i, "responses", j])) add(issue.loc, issue.msg)
      })
      if (rule.activeResponse >= (rule.responses?.length ?? 0))
        add(["rules", i, "activeResponse"], "No response at this index.")
    })
    if (Object.keys(errors).length > 0)
      return problem(422, "validation_failed", "Some fields need attention", { errors })

    const deleted = mode === "replace" ? db.rules.length : 0
    if (mode === "replace") db.rules = []
    for (const exported of file.rules) {
      const id = newId()
      const serviceId = exported.serviceName
        ? (db.services.find((s) => s.name === exported.serviceName)?.id ?? null)
        : null
      const responses = exported.responses.map((r) => toResponse(id, r))
      const rule: MockRule = {
        id,
        developerId: db.developer.id,
        ...ruleFields({ ...exported, serviceId, method: exported.method as never }),
        isEnabled: exported.isEnabled ?? true,
        activeResponseId: responses[exported.activeResponse ?? 0]?.id ?? responses[0]!.id,
        responses,
        createdAt: now(),
        updatedAt: now(),
      }
      db.rules.push(rule)
    }
    persist()
    return HttpResponse.json({ mode, created: file.rules.length, deleted })
  }),
]
