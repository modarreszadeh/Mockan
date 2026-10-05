/**
 * Gateway match precedence (docs/agent/mockan-architecture.md §7.2), used to sort rule lists so the order on
 * screen matches which rule wins: priority ↑, match type rank, longer pattern, older rule first.
 */
import type { MatchType, MockRule } from "@/api/types"

export const MATCH_TYPE_RANK: Record<MatchType, number> = {
  Exact: 0,
  Template: 1,
  Prefix: 2,
  Regex: 3,
}

type PrecedenceFields = Pick<MockRule, "priority" | "matchType" | "pattern" | "createdAt">

export function comparePrecedence(a: PrecedenceFields, b: PrecedenceFields): number {
  return (
    a.priority - b.priority ||
    MATCH_TYPE_RANK[a.matchType] - MATCH_TYPE_RANK[b.matchType] ||
    b.pattern.length - a.pattern.length ||
    Date.parse(a.createdAt) - Date.parse(b.createdAt)
  )
}

export const sortByPrecedence = <T extends PrecedenceFields>(rules: readonly T[]): T[] =>
  [...rules].sort(comparePrecedence)
