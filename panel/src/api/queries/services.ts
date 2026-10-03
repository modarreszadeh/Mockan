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
