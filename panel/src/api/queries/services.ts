/** Service catalog (`/services*`) and per-Developer environment choice (`/me/service-settings`). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, ApiError } from "../client"
import type {
  DeveloperServiceSetting,
  Service,
  ServiceEnvironment,
  ServiceEnvironmentInput,
  ServiceInput,
} from "../types"
import { serviceKeys, serviceSettingKeys } from "./keys"

export function useServices() {
  return useQuery({
    queryKey: serviceKeys.list(),
    queryFn: ({ signal }) => api.get<Service[]>("/services", signal),
    staleTime: 60_000,
  })
}

export function useServiceSettings() {
  return useQuery({
    queryKey: serviceSettingKeys.all,
    queryFn: ({ signal }) => api.get<DeveloperServiceSetting[]>("/me/service-settings", signal),
  })
}

/** The ServiceEnvironment the Developer's gateway uses for a Service (absent setting = Service default). */
export function selectedEnvironment(
  service: Service,
  settings: readonly DeveloperServiceSetting[] | undefined,
): ServiceEnvironment | undefined {
  const chosen = settings?.find((s) => s.serviceId === service.id)
  return (
    service.environments.find((e) => e.id === chosen?.serviceEnvironmentId) ??
    service.environments.find((e) => e.environment === service.defaultEnvironment) ??
    service.environments[0]
  )
}

/** Optimistic environment switch (PR-04). TODO(OQ-F5): PUT body is the full settings array. */
export function useUpdateServiceSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (settings: DeveloperServiceSetting[]) =>
      api.put<DeveloperServiceSetting[]>("/me/service-settings", settings),
    onMutate: async (settings) => {
      await queryClient.cancelQueries({ queryKey: serviceSettingKeys.all })
      const previous = queryClient.getQueryData<DeveloperServiceSetting[]>(serviceSettingKeys.all)
      queryClient.setQueryData(serviceSettingKeys.all, settings)
      return previous
    },
    onError: (error, _settings, previous) => {
      queryClient.setQueryData(serviceSettingKeys.all, previous)
      toast.error("Couldn't change the environment", {
        description: error instanceof ApiError ? error.message : "Check your connection and try again.",
      })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: serviceSettingKeys.all }),
  })
}

// ---- Admin catalog (PR-10). Non-admins get 403 from the API; the UI hides these controls. ----

function useCatalogMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: serviceKeys.all })
      void queryClient.invalidateQueries({ queryKey: serviceSettingKeys.all })
    },
  })
}

export const useCreateService = () => useCatalogMutation((input: ServiceInput) => api.post<Service>("/services", input))

export const useUpdateService = () =>
  useCatalogMutation(({ id, input }: { id: string; input: ServiceInput }) => api.put<Service>(`/services/${id}`, input))

export const useDeleteService = () => useCatalogMutation((id: string) => api.delete(`/services/${id}`))

export const useCreateEnvironment = () =>
  useCatalogMutation(({ serviceId, input }: { serviceId: string; input: ServiceEnvironmentInput }) =>
    api.post<ServiceEnvironment>(`/services/${serviceId}/environments`, input),
  )

export const useUpdateEnvironment = () =>
  useCatalogMutation(
    ({ serviceId, envId, input }: { serviceId: string; envId: string; input: ServiceEnvironmentInput }) =>
      api.put<ServiceEnvironment>(`/services/${serviceId}/environments/${envId}`, input),
  )

export const useDeleteEnvironment = () =>
  useCatalogMutation(({ serviceId, envId }: { serviceId: string; envId: string }) =>
    api.delete(`/services/${serviceId}/environments/${envId}`),
  )

/** Thrown by useSaveService: the step that failed, so field errors land on the right environment row. */
export class CatalogSaveError extends Error {
  readonly cause: unknown
  /** Set once the Service exists (a create that failed on an environment still created the Service). */
  readonly serviceId: string | undefined
  /** Index into the submitted environments, or undefined when the Service itself failed. */
  readonly environmentIndex: number | undefined

  constructor(cause: unknown, serviceId: string | undefined, environmentIndex: number | undefined) {
    super(cause instanceof Error ? cause.message : "Couldn't save the Service")
    this.name = "CatalogSaveError"
    this.cause = cause
    this.serviceId = serviceId
    this.environmentIndex = environmentIndex
  }
}

export interface SaveServiceInput {
  serviceId?: string
  service: ServiceInput
  /** Desired environments; `id` set for existing ones. Existing environments missing here are deleted. */
  environments: (ServiceEnvironmentInput & { id?: string })[]
  /** Environments the Service had when the form opened. */
  previous: ServiceEnvironment[]
}

/**
 * Create/update a Service and reconcile its environments (POST/PUT/DELETE per environment, arch §10).
 * Admin only (PR-10); the server enforces the upstream allowlist (PR-15).
 */
export function useSaveService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ serviceId, service, environments, previous }: SaveServiceInput): Promise<Service> => {
      let id = serviceId
      try {
        id = serviceId
          ? (await api.put<Service>(`/services/${serviceId}`, service)).id
          : (await api.post<Service>("/services", service)).id
      } catch (error) {
        throw new CatalogSaveError(error, serviceId, undefined)
      }
      const keep = new Set(environments.map((e) => e.id).filter(Boolean))
      for (const old of previous) {
        if (keep.has(old.id)) continue
        try {
          await api.delete(`/services/${id}/environments/${old.id}`)
        } catch (error) {
          throw new CatalogSaveError(error, id, undefined)
        }
      }
      for (const [index, { id: envId, ...input }] of environments.entries()) {
        try {
          if (envId) await api.put(`/services/${id}/environments/${envId}`, input)
          else await api.post(`/services/${id}/environments`, input)
        } catch (error) {
          throw new CatalogSaveError(error, id, index)
        }
      }
      const services = await api.get<Service[]>("/services")
      return services.find((s) => s.id === id)!
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: serviceKeys.all })
      void queryClient.invalidateQueries({ queryKey: serviceSettingKeys.all })
    },
  })
}
