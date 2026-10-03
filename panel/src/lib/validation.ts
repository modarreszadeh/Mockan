/**
 * Client-side validation that mirrors Agent/mockan-architecture.md §10. These are hints: the Admin API
 * decides (e.g. RE2 validity), and its field errors are mapped back onto the same form fields.
 * The MSW handlers reuse these rules so the dev backend behaves like the real one.
 */
import { z } from "zod"

import { ENVIRONMENTS, HTTP_METHODS, MATCH_TYPES, type MatchType } from "@/api/types"

// ---------------------------------------------------------------------------------------------
// DeveloperSlug (PR-01)

export const SLUG_PATTERN = /^[a-z][a-z0-9-]{1,31}$/
export const RESERVED_SLUGS: readonly string[] = ["api", "hubs", "health"]

/** Returns why a slug is invalid, or `null` when it is acceptable. */
export function slugProblem(slug: string): string | null {
  if (slug.length === 0) return "Enter a slug."
  if (slug.startsWith("_")) return "Slugs starting with “_” are reserved for Mockan."
  if (RESERVED_SLUGS.includes(slug)) return `“${slug}” is reserved. Pick another slug.`
  if (/[A-Z]/.test(slug)) return "Use lowercase letters only."
  if (!/^[a-z]/.test(slug)) return "Start with a lowercase letter."
  if (slug.length < 2) return "Use at least 2 characters."
  if (slug.length > 32) return "Use at most 32 characters."
  if (!SLUG_PATTERN.test(slug)) return "Use only lowercase letters, digits and hyphens."
  return null
}

export const slugSchema = z.string().superRefine((value, ctx) => {
  const problem = slugProblem(value)
  if (problem) ctx.addIssue({ code: "custom", message: problem })
})

// ---------------------------------------------------------------------------------------------
// Patterns (PR-05, D-17)

export const MAX_REGEX_LENGTH = 512
const TEMPLATE_PARAM = /^\{(\*?)([A-Za-z_][A-Za-z0-9_]*)\}$/

/** Returns why a pattern is invalid for the match type, or `null` when it looks valid. */
export function patternProblem(matchType: MatchType, pattern: string): string | null {
  if (pattern.trim().length === 0) return "Enter a pattern."
  if (matchType === "Regex") {
    if (pattern.length > MAX_REGEX_LENGTH) return `Regex patterns can be at most ${MAX_REGEX_LENGTH} characters.`
    if (/\(\?<?[=!]/.test(pattern)) return "RE2 doesn't support lookahead or lookbehind."
    if (/\\[1-9]|\\k</.test(pattern)) return "RE2 doesn't support backreferences."
    try {
      new RegExp(pattern)
    } catch (error) {
      return `Invalid regex: ${(error as Error).message.replace(/^Invalid regular expression: /, "")}`
    }
    return null
  }

  if (!pattern.startsWith("/")) return "Start the pattern with “/”."
  if (/\s/.test(pattern)) return "Patterns can't contain spaces."

  if (matchType === "Template") {
    const segments = pattern.split("/").slice(1)
    const names = new Set<string>()
    for (const [index, segment] of segments.entries()) {
      if (!segment.includes("{") && !segment.includes("}")) continue
      const match = TEMPLATE_PARAM.exec(segment)
      if (!match) return `“${segment}” isn't valid. Use {name} or {*name} as a whole segment.`
      const [, star, name] = match
      if (star && index !== segments.length - 1) return "{*name} can only be the last segment."
      if (names.has(name!)) return `Parameter {${name}} is used twice.`
      names.add(name!)
    }
  } else if (/[{}]/.test(pattern)) {
    return `${matchType} patterns can't contain { or }. Use Template for parameters.`
  }
  return null
}

// ---------------------------------------------------------------------------------------------
// Response (PR-06)

export const MIN_STATUS = 100
export const MAX_STATUS = 599
export const MAX_DELAY_MS = 30_000
export const MAX_BODY_BYTES = 1024 * 1024

export const byteLength = (text: string) => new TextEncoder().encode(text).length

export const isJsonContentType = (contentType: string) => /^application\/(.+\+)?json\b/i.test(contentType.trim())

export interface JsonProblem {
  line: number
  column: number
  message: string
}

/** Validates JSON and returns the error location (PR-06), or `null` when the text is valid JSON. */
export function jsonProblem(text: string): JsonProblem | null {
  try {
    JSON.parse(text)
    return null
  } catch (error) {
    const raw = (error as Error).message
    const message = raw
      .replace(/\s*\(line \d+ column \d+\)/, "")
      .replace(/ in JSON at position \d+/, "")
      .replace(/^JSON\.parse: /, "")
      .replace(/, ".*" is not valid JSON$/s, "")
    const lineCol = /line (\d+) column (\d+)/.exec(raw)
    if (lineCol) return { line: Number(lineCol[1]), column: Number(lineCol[2]), message }
    const position = /position (\d+)/.exec(raw)
    if (position) {
      const offset = Number(position[1])
      const before = text.slice(0, offset).split("\n")
      return { line: before.length, column: (before.at(-1)?.length ?? 0) + 1, message }
    }
    if (text.trim().length === 0) return { line: 1, column: 1, message: "Body is empty" }
    const lines = text.split("\n")
    return { line: lines.length, column: (lines.at(-1)?.length ?? 0) + 1, message }
  }
}

export const formatJsonProblem = (p: JsonProblem) => `Line ${p.line}, Col ${p.column}: ${p.message}`

export const statusCodeSchema = z
  .number({ error: "Enter a status code." })
  .int("Use a whole number.")
  .min(MIN_STATUS, `Use a status code from ${MIN_STATUS} to ${MAX_STATUS}.`)
  .max(MAX_STATUS, `Use a status code from ${MIN_STATUS} to ${MAX_STATUS}.`)

export const delaySchema = z
  .number({ error: "Enter a delay." })
  .int("Use whole milliseconds.")
  .min(0, "Delay can't be negative.")
  .max(MAX_DELAY_MS, `Delay can be at most ${MAX_DELAY_MS.toLocaleString("en-US")} ms.`)

// ---------------------------------------------------------------------------------------------
// Form schemas

/** A row of KeyValueEditor. Headers use `equals` only; conditions also allow `exists`. */
export const keyValueRowSchema = z.object({
  key: z.string(),
  operator: z.enum(["equals", "exists"]),
  value: z.string(),
})
export type KeyValueRow = z.infer<typeof keyValueRowSchema>

const conditionRows = z.array(keyValueRowSchema).superRefine((rows, ctx) => {
  rows.forEach((row, index) => {
    if (row.key.trim().length === 0 && row.value.trim().length > 0)
      ctx.addIssue({ code: "custom", message: "Enter a name.", path: [index, "key"] })
  })
})

export const responseFormSchema = z
  .object({
    id: z.string().optional(),
    name: z.string().trim().min(1, "Name the scenario.").max(100),
    statusCode: statusCodeSchema,
    contentType: z.string().trim().min(1, "Enter a content type."),
    headers: conditionRows,
    body: z.string(),
    delayMs: delaySchema,
  })
  .superRefine((value, ctx) => {
    if (byteLength(value.body) > MAX_BODY_BYTES)
      ctx.addIssue({ code: "custom", message: "Body can be at most 1 MB.", path: ["body"] })
    else if (isJsonContentType(value.contentType) && value.body.trim().length > 0) {
      const problem = jsonProblem(value.body)
      if (problem) ctx.addIssue({ code: "custom", message: formatJsonProblem(problem), path: ["body"] })
    }
  })
export type ResponseFormValues = z.infer<typeof responseFormSchema>

export const ruleFormSchema = z
  .object({
    name: z.string().trim().min(1, "Name the rule.").max(200, "Use at most 200 characters."),
    method: z.enum(HTTP_METHODS as [string, ...string[]]),
    matchType: z.enum(MATCH_TYPES as [MatchType, ...MatchType[]]),
    pattern: z.string(),
    serviceId: z.string(),
    priority: z.number({ error: "Enter a priority." }).int("Use a whole number.").min(0, "Use 0 or more."),
    queryConditions: conditionRows,
    headerConditions: conditionRows,
    response: responseFormSchema,
  })
  .superRefine((value, ctx) => {
    const problem = patternProblem(value.matchType, value.pattern)
    if (problem) ctx.addIssue({ code: "custom", message: problem, path: ["pattern"] })
  })
export type RuleFormValues = z.infer<typeof ruleFormSchema>

/** Allowed-origin glob, e.g. `http://localhost:*` (D-13). */
export function originProblem(origin: string): string | null {
  const value = origin.trim()
  if (value.length === 0) return "Enter an origin."
  if (!/^https?:\/\//.test(value)) return "Start with http:// or https://."
  if (/\s/.test(value)) return "Origins can't contain spaces."
  if (/\/$/.test(value) || /^https?:\/\/[^/]+\/./.test(value)) return "Use scheme, host and port only — no path."
  return null
}

export const settingsFormSchema = z.object({
  displayName: z.string().trim().min(1, "Enter your name.").max(100),
  allowedOrigins: z.array(
    z.object({
      value: z.string().superRefine((v, ctx) => {
        const problem = originProblem(v)
        if (problem) ctx.addIssue({ code: "custom", message: problem })
      }),
    }),
  ),
})
export type SettingsFormValues = z.infer<typeof settingsFormSchema>

export const environmentFormSchema = z.object({
  id: z.string().optional(),
  environment: z.enum(ENVIRONMENTS as ["dev", "stage"]),
  baseUrl: z
    .string()
    .trim()
    .min(1, "Enter a base URL.")
    .refine(
      (v) => /^https?:\/\/[^\s/]+/.test(v) && URL.canParse(v),
      "Enter a full URL, e.g. https://limsa.dev.internal.",
    ),
  timeoutSeconds: z.number({ error: "Enter a timeout." }).int().min(1, "Use at least 1 second.").max(3600),
  extraHeaders: conditionRows,
})
export type EnvironmentFormValues = z.infer<typeof environmentFormSchema>

export const serviceFormSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Enter a name.")
      .regex(/^[a-z][a-z0-9-]*$/, "Use lowercase letters, digits and hyphens, e.g. limsa."),
    pathPrefix: z
      .string()
      .trim()
      .regex(/^\/[A-Za-z0-9._~\-/]*[A-Za-z0-9._~-]$/, "Start with “/” and don't end with “/”, e.g. /limsa."),
    stripPrefix: z.boolean(),
    rewriteOrigin: z.boolean(),
    defaultEnvironment: z.enum(ENVIRONMENTS as ["dev", "stage"]),
    environments: z.array(environmentFormSchema).min(1, "Add at least one environment."),
  })
  .superRefine((value, ctx) => {
    const seen = new Set<string>()
    value.environments.forEach((env, index) => {
      if (seen.has(env.environment))
        ctx.addIssue({
          code: "custom",
          message: `${env.environment} is listed twice.`,
          path: ["environments", index, "environment"],
        })
      seen.add(env.environment)
    })
    if (!value.environments.some((env) => env.environment === value.defaultEnvironment))
      ctx.addIssue({
        code: "custom",
        message: "The default environment needs a base URL below.",
        path: ["defaultEnvironment"],
      })
  })
export type ServiceFormValues = z.infer<typeof serviceFormSchema>
