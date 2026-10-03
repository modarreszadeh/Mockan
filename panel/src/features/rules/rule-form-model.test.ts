import { describe, expect, it } from "vitest"

import { rulesFixture } from "@/mocks/fixtures"

import { ANY_SERVICE, formFieldFor, toFormValues, toSaveInput } from "./rule-form-model"

describe("rule form model", () => {
  it("round-trips a rule through the form", () => {
    const rule = rulesFixture().find((r) => r.name === "Notifications outage")!
    const values = toFormValues(rule)
    expect(values.headerConditions).toEqual([{ key: "X-Feature", operator: "equals", value: "beta" }])
    const input = toSaveInput(values, rule.id)
    expect(input.rule.headerConditions).toEqual(rule.headerConditions)
    expect(input.rule.serviceId).toBe(rule.serviceId)
    expect(input.response.id).toBe(rule.activeResponseId)
  })

  it("maps Any service to null and drops empty condition rows; exists has no value", () => {
    const values = toFormValues(rulesFixture()[5]!)
    values.serviceId = ANY_SERVICE
    values.queryConditions.push({ key: " ", operator: "equals", value: "" })
    const input = toSaveInput(values)
    expect(input.rule.serviceId).toBeNull()
    expect(input.rule.queryConditions).toEqual([{ key: "force", operator: "exists" }])
  })

  it("TODO(OQ-F1) maps API field paths onto form fields", () => {
    expect(formFieldFor("pattern")).toBe("pattern")
    expect(formFieldFor("responses.0.statusCode")).toBe("response.statusCode")
    expect(formFieldFor("response.delayMs")).toBe("response.delayMs")
    expect(formFieldFor("developerId")).toBeUndefined()
  })
})
