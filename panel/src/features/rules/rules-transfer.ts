/** Export / import of rules (FR-12, PR-14): reading an export file and explaining the server's problems with it. */
import type { FieldErrors } from "@/api/client"

export interface ParsedImport {
  /** The parsed file, sent to the server as is: the server validates every field. */
  file: { version: 1; rules: unknown[] }
  ruleCount: number
  responseCount: number
  names: string[]
}

export const MAX_IMPORT_RULES = 200

/** Cheap checks so an obviously wrong file never leaves the browser; the server stays the judge of everything else. */
export function parseImportFile(text: string): ParsedImport | { error: string } {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { error: "This isn't a JSON file. Choose a file exported from Mockan." }
  }
  if (!data || typeof data !== "object" || Array.isArray(data))
    return { error: "This file doesn't look like a Mockan export." }
  const { version, rules } = data as { version?: unknown; rules?: unknown }
  if (version !== 1)
    return { error: `Unsupported export version (${JSON.stringify(version) ?? "missing"}). Expected 1.` }
  if (!Array.isArray(rules)) return { error: "The file has no “rules” list." }
  if (rules.length === 0) return { error: "The file contains no rules." }
  if (rules.length > MAX_IMPORT_RULES) return { error: `At most ${MAX_IMPORT_RULES} rules can be imported at once.` }
  const items = rules as { name?: unknown; responses?: unknown }[]
  return {
    file: { version: 1, rules },
    ruleCount: rules.length,
    responseCount: items.reduce((sum, r) => sum + (Array.isArray(r?.responses) ? r.responses.length : 0), 0),
    names: items.map((r) => (typeof r?.name === "string" ? r.name : "")),
  }
}

/**
 * Turn the server's `rules.<i>.<field>` / `rules.<i>.responses.<j>.<field>` errors into readable lines:
 * `Rule 3 “Orders” → scenario 2 → body: Line 1: …`.
 */
export function describeImportErrors(fieldErrors: FieldErrors, names: readonly string[]): string[] {
  const lines: string[] = []
  for (const [path, messages] of Object.entries(fieldErrors)) {
    const parts = path.split(".")
    let label = path
    if (parts[0] === "rules" && /^\d+$/.test(parts[1] ?? "")) {
      const index = Number(parts[1])
      const name = names[index]
      label = `Rule ${index + 1}${name ? ` “${name}”` : ""}`
      const rest = parts.slice(2)
      if (rest[0] === "responses" && /^\d+$/.test(rest[1] ?? "")) {
        label += ` → scenario ${Number(rest[1]) + 1}`
        rest.splice(0, 2)
      }
      if (rest.length) label += ` → ${rest.join(".")}`
    }
    for (const message of messages) lines.push(`${label}: ${message}`)
  }
  return lines
}
