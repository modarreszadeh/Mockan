/** RFC 7807 problem+json helpers for the MSW handlers. */
import { HttpResponse } from "msw"

import { db } from "./db"

export function problem(
  status: number,
  code: string,
  title: string,
  extra: { detail?: string; errors?: Record<string, string[]> } = {},
) {
  return HttpResponse.json(
    { type: `https://mock.novin-tools.com/problems/${code}`, title, status, code, ...extra },
    { status, headers: { "Content-Type": "application/problem+json" } },
  )
}

/** FastAPI's default 422 shape — the other half of TODO(OQ-F1). */
export function fastApi422(issues: { loc: (string | number)[]; msg: string }[]) {
  return HttpResponse.json(
    { detail: issues.map(({ loc, msg }) => ({ loc: ["body", ...loc], msg, type: "value_error" })) },
    { status: 422 },
  )
}

export const unauthenticated = () => problem(401, "unauthenticated", "Sign in to continue")
export const forbidden = () => problem(403, "forbidden", "Only Mockan admins can change the Service catalog")
export const notFound = (what: string) => problem(404, "not_found", `${what} not found`)
export const readFailure = () =>
  problem(500, "internal_error", "Mockan couldn't load this", {
    detail: "The Admin API returned an error. Try again in a moment.",
  })

/** Guards shared by every handler; returns a response when the request must stop. */
export function guard(kind: "read" | "write" = "read") {
  if (!db.signedIn) return unauthenticated()
  if (kind === "read" && db.failReads) return readFailure()
  return undefined
}

export const now = () => new Date().toISOString()
export const newId = (): string => crypto.randomUUID()
