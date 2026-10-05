import { describe, expect, it } from "vitest"

// The same cases run against the server matcher in server/tests/matching/test_precedence_parity.py.
import fixture from "../../../server/tests/matching/precedence_parity.json"
import { sortByPrecedence } from "./precedence"
import type { MatchType } from "@/api/types"

interface ParityRule {
  id: string
  priority: number
  matchType: MatchType
  pattern: string
  createdAt: string
}

describe("PR-05 precedence parity with the Gateway (arch §7.2)", () => {
  for (const testCase of fixture.cases as { name: string; rules: ParityRule[]; order: string[] }[]) {
    it(testCase.name, () => {
      expect(sortByPrecedence(testCase.rules).map((rule) => rule.id)).toEqual(testCase.order)
    })
  }
})
