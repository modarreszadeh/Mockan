/**
 * Realistic fixtures for the MSW dev backend (prompt §6): Developer `ehtesham`, Services `identity`,
 * `limsa`, `portal`, and the dashboard rule from the PRD §6 journey.
 */
import type { Developer, DeveloperServiceSetting, MockResponse, MockRule, Service } from "@/api/types"
import { DEFAULT_ALLOWED_ORIGINS, PUBLIC_BASE_URL } from "@/lib/config"

/** Mirrors MOCKAN_ALLOWED_UPSTREAM_HOSTS (arch §12.3). `*.` wildcard allowed. */
export const ALLOWED_UPSTREAM_HOSTS = ["identity.stage.internal", "*.dev.internal", "*.stage.internal"]

/** Slugs other Developers already own. */
export const TAKEN_SLUGS = ["qoolak", "sara", "admin-team"]

const T0 = "2026-09-01T08:00:00.000Z"
/** Timestamps relative to now, so "Updated" reads naturally in the dev Panel. */
const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString()

export const DEVELOPER_ID = "0192f5a0-0000-7000-8000-00000000e001"

export function developerFixture(overrides: Partial<Developer> = {}): Developer {
  return {
    id: DEVELOPER_ID,
    slug: "ehtesham",
    displayName: "Ehtesham",
    allowedOrigins: [...DEFAULT_ALLOWED_ORIGINS],
    isEnabled: true,
    isAdmin: true,
    publicBaseUrl: PUBLIC_BASE_URL,
    createdAt: T0,
    updatedAt: T0,
    ...overrides,
  }
}

const SVC = {
  identity: "0192f5a0-0000-7000-8000-0000000051d1",
  limsa: "0192f5a0-0000-7000-8000-0000000051d2",
  portal: "0192f5a0-0000-7000-8000-0000000051d3",
}

const ENV = {
  identityDev: "0192f5a0-0000-7000-8000-00000000e4d1",
  identityStage: "0192f5a0-0000-7000-8000-00000000e4d2",
  limsaDev: "0192f5a0-0000-7000-8000-00000000e4d3",
  limsaStage: "0192f5a0-0000-7000-8000-00000000e4d4",
  portalStage: "0192f5a0-0000-7000-8000-00000000e4d5",
}

export function servicesFixture(): Service[] {
  const env = (
    id: string,
    serviceId: string,
    environment: "dev" | "stage",
    baseUrl: string,
    extraHeaders: Record<string, string> = {},
  ) => ({
    id,
    serviceId,
    environment,
    baseUrl,
    timeoutSeconds: 100,
    extraHeaders,
    createdAt: T0,
    updatedAt: T0,
  })
  return [
    {
      id: SVC.identity,
      name: "identity",
      pathPrefix: "/identity",
      stripPrefix: false,
      rewriteOrigin: false,
      defaultEnvironment: "stage",
      environments: [
        env(ENV.identityDev, SVC.identity, "dev", "https://identity.dev.internal"),
        env(ENV.identityStage, SVC.identity, "stage", "https://identity.stage.internal"),
      ],
      createdAt: T0,
      updatedAt: T0,
    },
    {
      id: SVC.limsa,
      name: "limsa",
      pathPrefix: "/limsa",
      stripPrefix: false,
      rewriteOrigin: false,
      defaultEnvironment: "stage",
      environments: [
        env(ENV.limsaDev, SVC.limsa, "dev", "https://limsa.dev.internal", { "X-Debug": "1" }),
        env(ENV.limsaStage, SVC.limsa, "stage", "https://limsa.stage.internal"),
      ],
      createdAt: T0,
      updatedAt: T0,
    },
    {
      id: SVC.portal,
      name: "portal",
      pathPrefix: "/portal",
      stripPrefix: true,
      rewriteOrigin: true,
      defaultEnvironment: "stage",
      environments: [env(ENV.portalStage, SVC.portal, "stage", "https://portal.stage.internal/api")],
      createdAt: T0,
      updatedAt: T0,
    },
  ]
}

export function serviceSettingsFixture(): DeveloperServiceSetting[] {
  return [{ serviceId: SVC.limsa, serviceEnvironmentId: ENV.limsaDev }]
}

export const DASHBOARD_BODY = JSON.stringify(
  {
    period: "2026-10",
    totals: { samples: 1284, pending: 37, approved: 1198, rejected: 49 },
    turnaroundHours: { p50: 18.5, p95: 41 },
    recentOrders: [
      { id: 4211, customer: "Pars Lab", status: "pending", receivedAt: "2026-10-02T14:12:00Z" },
      { id: 4210, customer: "Novin Clinic", status: "approved", receivedAt: "2026-10-02T11:40:00Z" },
    ],
  },
  null,
  2,
)

let responseCounter = 0
function response(
  ruleId: string,
  name: string,
  statusCode: number,
  body: string,
  delayMs = 0,
  headers: Record<string, string> = {},
): MockResponse {
  responseCounter += 1
  return {
    id: `0192f5a0-0000-7000-8000-${String(responseCounter).padStart(12, "0")}`,
    ruleId,
    name,
    statusCode,
    headers,
    contentType: "application/json",
    body,
    bodyMode: "Static",
    delayMs,
    createdAt: T0,
    updatedAt: T0,
  }
}

export function rulesFixture(): MockRule[] {
  responseCounter = 0
  const rule = (
    n: number,
    fields: Pick<MockRule, "name" | "method" | "matchType" | "pattern" | "isEnabled"> &
      Partial<MockRule> & { res: (id: string) => MockResponse },
  ): MockRule => {
    const id = `0192f5a0-0000-7000-8000-0000000a${String(n).padStart(4, "0")}`
    const { res, ...rest } = fields
    const r = res(id)
    return {
      id,
      developerId: DEVELOPER_ID,
      serviceId: null,
      queryConditions: [],
      headerConditions: [],
      priority: 100,
      activeResponseId: r.id,
      responses: [r],
      createdAt: hoursAgo((10 - n) * 24),
      updatedAt: hoursAgo(n * 7 + 1),
      ...rest,
    }
  }
  return [
    rule(1, {
      name: "Limsa dashboard",
      method: "GET",
      matchType: "Exact",
      pattern: "/limsa/api/v1/dashboard",
      serviceId: SVC.limsa,
      isEnabled: true,
      res: (id) => response(id, "success", 200, DASHBOARD_BODY, 300),
    }),
    rule(2, {
      name: "Order details",
      method: "GET",
      matchType: "Template",
      pattern: "/limsa/api/v1/orders/{id}",
      serviceId: SVC.limsa,
      isEnabled: false,
      res: (id) => response(id, "success", 200, JSON.stringify({ id: 42, status: "pending", items: [] }, null, 2)),
    }),
    rule(3, {
      name: "Reports (all)",
      method: "ANY",
      matchType: "Prefix",
      pattern: "/limsa/api/v1/reports/",
      serviceId: SVC.limsa,
      isEnabled: true,
      res: (id) => response(id, "empty", 200, JSON.stringify({ items: [], total: 0 }, null, 2)),
    }),
    rule(4, {
      name: "Items not found",
      method: "GET",
      matchType: "Regex",
      pattern: "^/limsa/api/v1/(items|goods)/\\d+$",
      serviceId: SVC.limsa,
      priority: 50,
      isEnabled: true,
      res: (id) =>
        response(id, "error-404", 404, JSON.stringify({ title: "Not found", status: 404 }, null, 2), 0, {
          "Cache-Control": "no-store",
        }),
    }),
    rule(5, {
      name: "Notifications outage",
      method: "POST",
      matchType: "Exact",
      pattern: "/portal/api/notifications",
      serviceId: SVC.portal,
      headerConditions: [{ key: "X-Feature", operator: "equals", value: "beta" }],
      isEnabled: false,
      res: (id) => response(id, "error-500", 500, JSON.stringify({ title: "Internal error" }, null, 2), 1000),
    }),
    rule(6, {
      name: "Delete draft",
      method: "DELETE",
      matchType: "Template",
      pattern: "/limsa/api/v1/drafts/{draftId}",
      queryConditions: [{ key: "force", operator: "exists" }],
      isEnabled: true,
      res: (id) => ({ ...response(id, "no-content", 204, ""), contentType: "text/plain" }),
    }),
  ]
}
