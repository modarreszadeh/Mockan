/**
 * The one `fetch` wrapper for the Admin API (prompt §6): base `/api/v1`, cookies included, JSON in/out,
 * `401` → full-page redirect to SSO login, non-2xx → `ApiError` carrying the parsed problem+json.
 */
import type { ProblemDetails } from "./types"

export const API_BASE = "/api/v1"
export const LOGIN_URL = `${API_BASE}/auth/login`

/** Field path (camelCase, dot-separated, e.g. `responses.0.statusCode`) → messages. */
export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  readonly status: number
  readonly problem: ProblemDetails
  readonly fieldErrors: FieldErrors

  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? `Request failed with status ${status}`)
    this.name = "ApiError"
    this.status = status
    this.problem = problem
    this.fieldErrors = extractFieldErrors(problem)
  }

  get code(): string | undefined {
    return typeof this.problem.code === "string" ? this.problem.code : undefined
  }
}

const snakeToCamel = (segment: string) => segment.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())

function pathFromParts(parts: readonly (string | number)[]): string {
  return parts.map((p) => (typeof p === "number" ? String(p) : snakeToCamel(p))).join(".")
}

/**
 * Supports both field-error shapes until the backend settles on one.
 * TODO(OQ-F1): problem+json `errors: { field: [messages] }` and FastAPI's default `422 detail: [{ loc, msg }]`.
 */
export function extractFieldErrors(problem: ProblemDetails): FieldErrors {
  const result: FieldErrors = {}
  const add = (field: string, message: string) => {
    ;(result[field] ??= []).push(message)
  }

  if (problem.errors && typeof problem.errors === "object") {
    for (const [field, messages] of Object.entries(problem.errors)) {
      const path = pathFromParts(field.split("."))
      for (const message of Array.isArray(messages) ? messages : [String(messages)]) add(path, message)
    }
  }

  const detail: unknown = problem.detail
  if (Array.isArray(detail)) {
    for (const item of detail) {
      if (!item || typeof item !== "object") continue
      const { loc, msg } = item as { loc?: unknown; msg?: unknown }
      if (!Array.isArray(loc) || typeof msg !== "string") continue
      const parts = (loc as (string | number)[]).filter(
        (p, i) => !(i === 0 && (p === "body" || p === "query" || p === "path")),
      )
      if (parts.length > 0) add(pathFromParts(parts), msg)
    }
  }
  return result
}

async function parseProblem(response: Response): Promise<ProblemDetails> {
  const text = await response.text()
  if (!text) return { status: response.status, title: response.statusText }
  try {
    const parsed: unknown = JSON.parse(text)
    if (parsed && typeof parsed === "object") {
      const problem = parsed as ProblemDetails
      // FastAPI's default 422 puts the field list in `detail`; keep a readable message too.
      if (Array.isArray(problem.detail)) {
        return { title: "Validation failed", status: response.status, ...problem }
      }
      return { status: response.status, ...problem }
    }
  } catch {
    // Not JSON — fall through.
  }
  return { status: response.status, title: response.statusText, detail: text }
}

export function redirectToLogin() {
  window.location.assign(LOGIN_URL)
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE"
  body?: unknown
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options
  // Absolute URL so the same code runs in the browser and in Vitest (Node's fetch rejects relative URLs).
  const response = await fetch(new URL(`${API_BASE}${path}`, window.location.origin), {
    method,
    credentials: "include",
    headers: {
      Accept: "application/json, application/problem+json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  })

  if (response.status === 401) {
    redirectToLogin()
    throw new ApiError(401, { status: 401, title: "Signing you in…", code: "unauthenticated" })
  }
  if (!response.ok) throw new ApiError(response.status, await parseProblem(response))
  if (response.status === 204) return undefined as T

  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  delete: <T = void>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
}
