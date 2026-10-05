/**
 * Plain (zod-free) checks that mirror docs/agent/mockan-architecture.md §10. Kept separate from the zod schemas in
 * validation.ts so components can use them without pulling zod into the initial bundle.
 */
import type { MatchType } from "@/api/types"

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

/** Allowed-origin glob, e.g. `http://localhost:*` (D-13). */
export function originProblem(origin: string): string | null {
  const value = origin.trim()
  if (value.length === 0) return "Enter an origin."
  if (!/^https?:\/\//.test(value)) return "Start with http:// or https://."
  if (/\s/.test(value)) return "Origins can't contain spaces."
  if (/\/$/.test(value) || /^https?:\/\/[^/]+\/./.test(value)) return "Use scheme, host and port only — no path."
  return null
}
