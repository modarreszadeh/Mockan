/**
 * Client-side validation that mirrors Agent/mockan-architecture.md §10. These are hints: the Admin API
 * decides (e.g. RE2 validity), and its field errors are mapped back onto the same form fields.
 * The MSW handlers reuse these rules so the dev backend behaves like the real one.
 */
import { z } from "zod"

import { BODY_MODES, ENVIRONMENTS, HTTP_METHODS, MATCH_TYPES, type BodyMode, type MatchType } from "@/api/types"

import {
  byteLength,
  formatJsonProblem,
  isJsonContentType,
  jsonProblem,
  MAX_BODY_BYTES,
  MAX_DELAY_MS,
  MAX_STATUS,
  MIN_STATUS,
  originProblem,
  patternProblem,
  slugProblem,
} from "./checks"

export * from "./checks"

export const slugSchema = z.string().superRefine((value, ctx) => {
  const problem = slugProblem(value)
  if (problem) ctx.addIssue({ code: "custom", message: problem })
})

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
    bodyMode: z.enum(BODY_MODES as [BodyMode, ...BodyMode[]]),
    delayMs: delaySchema,
  })
  .superRefine((value, ctx) => {
    if (byteLength(value.body) > MAX_BODY_BYTES)
      ctx.addIssue({ code: "custom", message: "Body can be at most 1 MB.", path: ["body"] })
    // A Template body isn't JSON until it is rendered; the server checks its syntax on save (PR-19).
    else if (value.bodyMode === "Static" && isJsonContentType(value.contentType) && value.body.trim().length > 0) {
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
      // "/" alone is the catch-all Service; otherwise start with "/" and don't end with one.
      .regex(
        /^(?:\/|\/[A-Za-z0-9._~\-/]*[A-Za-z0-9._~-])$/,
        "Start with “/” and don't end with “/”, e.g. /limsa. Just “/” matches every path.",
      ),
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
