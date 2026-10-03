/** Service catalog (admin writes) and `/me/service-settings` (arch §10, PR-04, PR-10, PR-15). */
import { delay, http, HttpResponse } from "msw"

import type { DeveloperServiceSetting, Service, ServiceEnvironmentInput, ServiceInput } from "@/api/types"

import { db, persist } from "../db"
import { ALLOWED_UPSTREAM_HOSTS } from "../fixtures"
import { forbidden, guard, newId, notFound, now, problem } from "../problem"

export const ALLOWLIST_MESSAGE = "Only allowlisted dev/stage hosts can be used."

export function hostAllowed(baseUrl: string): boolean {
  let host: string
  try {
    host = new URL(baseUrl).hostname
  } catch {
    return false
  }
  return ALLOWED_UPSTREAM_HOSTS.some((allowed) =>
    allowed.startsWith("*.") ? host.endsWith(allowed.slice(1)) : host === allowed,
  )
}

function adminGuard() {
  return guard("write") ?? (db.developer.isAdmin ? undefined : forbidden())
}

function validateService(input: ServiceInput, selfId?: string) {
  const errors: Record<string, string[]> = {}
  if (!input.name?.trim()) errors.name = ["Enter a name."]
  if (!input.pathPrefix?.startsWith("/")) errors.path_prefix = ["Start the path prefix with “/”."]
  if (db.services.some((s) => s.id !== selfId && s.name === input.name))
    errors.name = [`A Service named “${input.name}” already exists.`]
  if (db.services.some((s) => s.id !== selfId && s.pathPrefix.toLowerCase() === input.pathPrefix?.toLowerCase()))
    errors.path_prefix = [`Path prefix ${input.pathPrefix} is already used by another Service.`]
  return errors
}

function validateEnvironment(service: Service, input: ServiceEnvironmentInput, selfId?: string) {
  const errors: Record<string, string[]> = {}
  if (!hostAllowed(input.baseUrl)) errors.base_url = [ALLOWLIST_MESSAGE]
  if (service.environments.some((e) => e.id !== selfId && e.environment === input.environment))
    errors.environment = [`${service.name} already has a ${input.environment} environment.`]
  if (!Number.isInteger(input.timeoutSeconds) || input.timeoutSeconds < 1)
    errors.timeout_seconds = ["Use at least 1 second."]
  return errors
}

const invalid = (errors: Record<string, string[]>) =>
  errors.base_url
    ? problem(422, "upstream_host_not_allowed", "Upstream host not allowed", {
        detail: "The base URL's host is not in MOCKAN_ALLOWED_UPSTREAM_HOSTS.",
        errors,
      })
    : problem(
        Object.values(errors).some((m) => m[0]?.includes("already")) ? 409 : 422,
        "validation_failed",
        "Some fields need attention",
        { errors },
      )

const findService = (id: string | readonly string[] | undefined) => db.services.find((s) => s.id === id)

export const serviceHandlers = [
  http.get("*/api/v1/services", async () => {
    await delay()
    return guard() ?? HttpResponse.json(db.services)
  }),

  http.post("*/api/v1/services", async ({ request }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    const input = (await request.json()) as ServiceInput
    const errors = validateService(input)
    if (Object.keys(errors).length) return invalid(errors)
    const service: Service = { id: newId(), ...input, environments: [], createdAt: now(), updatedAt: now() }
    db.services.push(service)
    persist()
    return HttpResponse.json(service, { status: 201 })
  }),

  http.put("*/api/v1/services/:id", async ({ params, request }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    const service = findService(params.id)
    if (!service) return notFound("Service")
    const input = (await request.json()) as ServiceInput
    const errors = validateService(input, service.id)
    if (Object.keys(errors).length) return invalid(errors)
    Object.assign(service, input, { updatedAt: now() })
    persist()
    return HttpResponse.json(service)
  }),

  http.delete("*/api/v1/services/:id", async ({ params }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    if (!findService(params.id)) return notFound("Service")
    db.services = db.services.filter((s) => s.id !== params.id)
    db.serviceSettings = db.serviceSettings.filter((s) => s.serviceId !== params.id)
    db.rules = db.rules.map((r) => (r.serviceId === params.id ? { ...r, serviceId: null } : r))
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.post("*/api/v1/services/:id/environments", async ({ params, request }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    const service = findService(params.id)
    if (!service) return notFound("Service")
    const input = (await request.json()) as ServiceEnvironmentInput
    const errors = validateEnvironment(service, input)
    if (Object.keys(errors).length) return invalid(errors)
    const environment = { id: newId(), serviceId: service.id, ...input, createdAt: now(), updatedAt: now() }
    service.environments.push(environment)
    persist()
    return HttpResponse.json(environment, { status: 201 })
  }),

  http.put("*/api/v1/services/:id/environments/:envId", async ({ params, request }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    const service = findService(params.id)
    const environment = service?.environments.find((e) => e.id === params.envId)
    if (!service || !environment) return notFound("ServiceEnvironment")
    const input = (await request.json()) as ServiceEnvironmentInput
    const errors = validateEnvironment(service, input, environment.id)
    if (Object.keys(errors).length) return invalid(errors)
    Object.assign(environment, input, { updatedAt: now() })
    persist()
    return HttpResponse.json(environment)
  }),

  http.delete("*/api/v1/services/:id/environments/:envId", async ({ params }) => {
    await delay()
    const stop = adminGuard()
    if (stop) return stop
    const service = findService(params.id)
    if (!service?.environments.some((e) => e.id === params.envId)) return notFound("ServiceEnvironment")
    service.environments = service.environments.filter((e) => e.id !== params.envId)
    db.serviceSettings = db.serviceSettings.filter((s) => s.serviceEnvironmentId !== params.envId)
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.get("*/api/v1/me/service-settings", async () => {
    await delay()
    return guard() ?? HttpResponse.json(db.serviceSettings)
  }),

  // TODO(OQ-F5): body is the full DeveloperServiceSetting[]; absent Service = its default environment.
  http.put("*/api/v1/me/service-settings", async ({ request }) => {
    await delay()
    const stop = guard("write")
    if (stop) return stop
    const settings = (await request.json()) as DeveloperServiceSetting[]
    for (const setting of settings) {
      const service = findService(setting.serviceId)
      if (!service?.environments.some((e) => e.id === setting.serviceEnvironmentId))
        return problem(422, "validation_failed", "Unknown Service or ServiceEnvironment", {
          detail: `ServiceEnvironment ${setting.serviceEnvironmentId} doesn't belong to Service ${setting.serviceId}.`,
        })
    }
    db.serviceSettings = settings
    persist()
    return HttpResponse.json(db.serviceSettings)
  }),
]
