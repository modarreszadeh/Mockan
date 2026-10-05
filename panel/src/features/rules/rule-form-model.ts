/** Mapping between the rule editor form (RuleFormValues) and the Admin API payloads. */
import type { FieldPath } from "react-hook-form"

import { activeResponse } from "@/api/queries/rules"
import type { SaveRuleInput } from "@/api/queries/rules"
import type { Condition, HttpMethodOrAny, MockResponse, MockRule } from "@/api/types"
import { recordToRows, rowsToRecord } from "@/lib/format"
import type { KeyValueRow, ResponseFormValues, RuleFormValues } from "@/lib/validation"

/** Sentinel for "Any service" in the scope select (Radix Select can't use an empty value). */
export const ANY_SERVICE = "__any"

export const NEW_RULE_DEFAULTS: RuleFormValues = {
  name: "",
  method: "GET",
  matchType: "Exact",
  pattern: "",
  serviceId: ANY_SERVICE,
  priority: 100,
  queryConditions: [],
  headerConditions: [],
  response: {
    name: "success",
    statusCode: 200,
    contentType: "application/json",
    headers: [],
    body: "",
    bodyMode: "Static",
    delayMs: 0,
  },
}

const conditionToRow = (c: Condition): KeyValueRow => ({ key: c.key, operator: c.operator, value: c.value ?? "" })

const rowToCondition = (row: KeyValueRow): Condition =>
  row.operator === "exists"
    ? { key: row.key.trim(), operator: "exists" }
    : { key: row.key.trim(), operator: "equals", value: row.value }

export const toResponseFormValues = (response: MockResponse): ResponseFormValues => ({
  id: response.id,
  name: response.name,
  statusCode: response.statusCode,
  contentType: response.contentType,
  headers: recordToRows(response.headers),
  body: response.body,
  bodyMode: response.bodyMode,
  delayMs: response.delayMs,
})

/** The editor shows one scenario at a time: `responseId` (default: the active one) fills `response`. */
export function toFormValues(rule: MockRule, responseId?: string): RuleFormValues {
  const response = rule.responses.find((r) => r.id === responseId) ?? activeResponse(rule)
  return {
    name: rule.name,
    method: rule.method,
    matchType: rule.matchType,
    pattern: rule.pattern,
    serviceId: rule.serviceId ?? ANY_SERVICE,
    priority: rule.priority,
    queryConditions: rule.queryConditions.map(conditionToRow),
    headerConditions: rule.headerConditions.map(conditionToRow),
    response: response ? toResponseFormValues(response) : NEW_RULE_DEFAULTS.response,
  }
}

export function toSaveInput(values: RuleFormValues, ruleId?: string): SaveRuleInput {
  const keep = (rows: KeyValueRow[]) => rows.filter((r) => r.key.trim().length > 0)
  return {
    ruleId,
    rule: {
      name: values.name.trim(),
      method: values.method as HttpMethodOrAny,
      matchType: values.matchType,
      pattern: values.pattern.trim(),
      serviceId: values.serviceId === ANY_SERVICE ? null : values.serviceId,
      priority: values.priority,
      queryConditions: keep(values.queryConditions).map(rowToCondition),
      headerConditions: keep(values.headerConditions).map(rowToCondition),
    },
    response: {
      id: values.response.id,
      name: values.response.name.trim(),
      statusCode: values.response.statusCode,
      contentType: values.response.contentType.trim(),
      headers: rowsToRecord(values.response.headers),
      body: values.response.body,
      bodyMode: values.response.bodyMode,
      delayMs: values.response.delayMs,
    },
  }
}

const RESPONSE_FIELDS = new Set(["name", "statusCode", "contentType", "headers", "body", "bodyMode", "delayMs"])
const RULE_FIELDS = new Set([
  "name",
  "method",
  "matchType",
  "pattern",
  "serviceId",
  "priority",
  "queryConditions",
  "headerConditions",
])

/**
 * Map an API field path (camelCase, from ApiError.fieldErrors) onto a form field, or `undefined` when the form
 * has no such field. `responses.0.x` (create) and `response.x` (update) both land on `response.x`.
 */
export function formFieldFor(apiPath: string): FieldPath<RuleFormValues> | undefined {
  const parts = apiPath.split(".")
  if ((parts[0] === "responses" && parts[1] === "0") || parts[0] === "response") {
    const rest = parts[0] === "responses" ? parts.slice(2) : parts.slice(1)
    if (rest[0] && RESPONSE_FIELDS.has(rest[0])) return `response.${rest.join(".")}` as FieldPath<RuleFormValues>
    return undefined
  }
  if (parts[0] && RULE_FIELDS.has(parts[0])) return apiPath as FieldPath<RuleFormValues>
  return undefined
}
