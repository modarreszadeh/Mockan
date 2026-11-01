/**
 * `/shared/rules/:token` (S-3): public, so no session guard. The token is looked up on the rules in the db;
 * an unknown or revoked one is the same 404 the real API returns.
 */
import { delay, http, HttpResponse } from "msw"

import type { SharedRule } from "@/api/types"

import { db } from "../db"
import { notFound } from "../problem"

export const sharedHandlers = [
  http.get("*/api/v1/shared/rules/:token", async ({ params }) => {
    await delay()
    const rule = db.rules.find((r) => r.shareToken !== null && r.shareToken === params.token)
    if (!rule) return notFound("Shared rule")
    const service = db.services.find((s) => s.id === rule.serviceId)
    const body: SharedRule = {
      name: rule.name,
      method: rule.method,
      matchType: rule.matchType,
      pattern: rule.pattern,
      queryConditions: rule.queryConditions,
      headerConditions: rule.headerConditions,
      priority: rule.priority,
      isEnabled: rule.isEnabled,
      activeResponseId: rule.activeResponseId,
      responses: rule.responses,
      service: service ? { name: service.name, pathPrefix: service.pathPrefix } : null,
      owner: { displayName: db.developer.displayName, slug: db.developer.slug },
      publicBaseUrl: db.developer.publicBaseUrl,
      updatedAt: rule.updatedAt,
    }
    return HttpResponse.json(body, { headers: { "Cache-Control": "no-store" } })
  }),
]
