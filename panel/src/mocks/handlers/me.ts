/** `GET/PUT /me` with arch §10 slug rules. */
import { delay, http, HttpResponse } from "msw"

import type { DeveloperUpdate } from "@/api/types"
import { originProblem, slugProblem } from "@/lib/validation"

import { db, persist } from "../db"
import { TAKEN_SLUGS } from "../fixtures"
import { guard, now, problem } from "../problem"

export const meHandlers = [
  http.get("*/api/v1/me", async () => {
    await delay()
    return guard() ?? HttpResponse.json(db.developer)
  }),

  http.put("*/api/v1/me", async ({ request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const update = (await request.json()) as DeveloperUpdate
    const errors: Record<string, string[]> = {}

    if (update.slug !== undefined && update.slug !== db.developer.slug) {
      if (db.developer.slug !== null)
        return problem(409, "slug_immutable", "Your slug can't be changed", {
          errors: { slug: ["Your workspace slug is already set and can't be changed."] },
        })
      const slugIssue = slugProblem(update.slug)
      if (slugIssue) errors.slug = [slugIssue]
      else if (TAKEN_SLUGS.includes(update.slug))
        return problem(409, "slug_taken", "Slug already in use", {
          errors: { slug: [`“${update.slug}” is already taken. Try another one.`] },
        })
    }
    if (update.displayName !== undefined && update.displayName.trim().length === 0)
      errors.displayName = ["Enter your name."]
    if (update.allowedOrigins !== undefined) {
      update.allowedOrigins.forEach((origin, index) => {
        const issue = originProblem(origin)
        if (issue) errors[`allowedOrigins.${index}`] = [issue]
      })
    }
    if (Object.keys(errors).length > 0)
      return problem(422, "validation_failed", "Some fields need attention", { errors })

    db.developer = {
      ...db.developer,
      ...(update.slug !== undefined ? { slug: update.slug } : {}),
      ...(update.displayName !== undefined ? { displayName: update.displayName.trim() } : {}),
      ...(update.allowedOrigins !== undefined ? { allowedOrigins: update.allowedOrigins } : {}),
      updatedAt: now(),
    }
    persist()
    return HttpResponse.json(db.developer)
  }),
]
