/**
 * Admin API types, hand-written from Agent/mockan-architecture.md §8 (camelCase on the wire, §10).
 *
 * The contract is documented in Backend/admin-api.md and pinned by `server/tests/admin/openapi.snapshot.json`
 * (OQ-F5 resolved); change these types in the same commit as that snapshot.
 */

export type MatchType = "Exact" | "Template" | "Prefix" | "Regex"

export const MATCH_TYPES: readonly MatchType[] = ["Exact", "Template", "Prefix", "Regex"]

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS"
export type HttpMethodOrAny = "ANY" | HttpMethod

export const HTTP_METHODS: readonly HttpMethodOrAny[] = [
  "ANY",
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
]

export type EnvironmentName = "dev" | "stage"

export const ENVIRONMENTS: readonly EnvironmentName[] = ["dev", "stage"]

export type BodyMode = "Static" | "Template" | "ProxyAndPatch"

export type RequestSource = "Proxied" | "Mocked" | "Error"

export type ConditionOperator = "equals" | "exists"

/** One query or header condition (arch §7.1). `value` is ignored when `operator` is `exists`. */
export interface Condition {
  key: string
  operator: ConditionOperator
  value?: string
}

export interface Developer {
  id: string
  /** `null` until the Developer claims a DeveloperSlug (PR-01). */
  slug: string | null
  displayName: string
  allowedOrigins: string[]
  isEnabled: boolean
  isAdmin: boolean
  /** Read-only: the Gateway's public URL (`MOCKAN_PUBLIC_BASE_URL`, OQ-F4). */
  publicBaseUrl: string
  createdAt: string
  updatedAt: string
}

/** Body of `PUT /me`. `slug` can only be set while it is still `null`. */
export interface DeveloperUpdate {
  slug?: string
  displayName?: string
  allowedOrigins?: string[]
}

export interface ServiceEnvironment {
  id: string
  serviceId: string
  environment: EnvironmentName
  baseUrl: string
  timeoutSeconds: number
  extraHeaders: Record<string, string>
  createdAt: string
  updatedAt: string
}

export type ServiceEnvironmentInput = Pick<
  ServiceEnvironment,
  "environment" | "baseUrl" | "timeoutSeconds" | "extraHeaders"
>

export interface Service {
  id: string
  name: string
  pathPrefix: string
  stripPrefix: boolean
  rewriteOrigin: boolean
  defaultEnvironment: EnvironmentName
  environments: ServiceEnvironment[]
  createdAt: string
  updatedAt: string
}

export type ServiceInput = Pick<Service, "name" | "pathPrefix" | "stripPrefix" | "rewriteOrigin" | "defaultEnvironment">

/** A row of `developer_service_settings`. No row for a Service = the Service default environment. */
export interface DeveloperServiceSetting {
  serviceId: string
  serviceEnvironmentId: string
}

export interface MockResponse {
  id: string
  ruleId: string
  /** UI label: Scenario. */
  name: string
  statusCode: number
  headers: Record<string, string>
  contentType: string
  body: string
  bodyMode: BodyMode
  delayMs: number
  createdAt: string
  updatedAt: string
}

export type MockResponseInput = Pick<
  MockResponse,
  "name" | "statusCode" | "headers" | "contentType" | "body" | "delayMs"
> & { bodyMode?: BodyMode }

/** What a Developer can pick in the editor; `ProxyAndPatch` is Phase 3 (the API answers 422). */
export const BODY_MODES: readonly BodyMode[] = ["Static", "Template"]

export interface MockRule {
  id: string
  developerId: string
  serviceId: string | null
  name: string
  method: HttpMethodOrAny
  matchType: MatchType
  pattern: string
  queryConditions: Condition[]
  headerConditions: Condition[]
  priority: number
  isEnabled: boolean
  activeResponseId: string | null
  /** TODO(OQ-F5): assumed to be embedded in rule payloads. */
  responses: MockResponse[]
  createdAt: string
  updatedAt: string
}

export type MockRuleUpdate = Pick<
  MockRule,
  "serviceId" | "name" | "method" | "matchType" | "pattern" | "queryConditions" | "headerConditions" | "priority"
> & { isEnabled?: boolean }

/** Body of `POST /me/rules`. The first response becomes the active one. */
export type MockRuleCreate = MockRuleUpdate & { responses: MockResponseInput[] }

export interface ToggleAllResult {
  updated: number
}

/** Phase 2 (PR-12). Headers and bodies arrive already masked (NFR-07); never unmask them. */
export interface RequestLogEntry {
  id: number
  developerId: string
  timestamp: string
  method: string
  path: string
  query: string
  serviceId: string | null
  source: RequestSource
  ruleId: string | null
  statusCode: number
  durationMs: number
  requestHeaders: Record<string, string>
  responseHeaders: Record<string, string>
  requestBodySample: string | null
  responseBodySample: string | null
}

/** RFC 7807 problem+json as returned by the Admin API. */
export interface ProblemDetails {
  type?: string
  title?: string
  status?: number
  detail?: string
  code?: string
  instance?: string
  /** TODO(OQ-F1): one of two possible field-error shapes. */
  errors?: Record<string, string[]>
  [key: string]: unknown
}
