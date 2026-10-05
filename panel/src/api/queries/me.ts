/** `GET/PUT /me` and logout. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, LOGIN_PAGE_URL } from "../client"
import { PUBLIC_BASE_URL } from "@/lib/config"

import type { Developer, DeveloperUpdate } from "../types"
import { meKeys } from "./keys"

export const fetchMe = (signal?: AbortSignal) => api.get<Developer>("/me", signal)

export function useMe() {
  return useQuery({ queryKey: meKeys.all, queryFn: ({ signal }) => fetchMe(signal), staleTime: 60_000 })
}

/** The Gateway's public URL from `GET /me` (OQ-F4); the build-time value until the Developer has loaded. */
export function usePublicBaseUrl(): string {
  const { data } = useMe()
  return data?.publicBaseUrl || PUBLIC_BASE_URL
}

export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (update: DeveloperUpdate) => api.put<Developer>("/me", update),
    onSuccess: (developer) => queryClient.setQueryData(meKeys.all, developer),
  })
}

export function useLogout() {
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSettled: () => window.location.assign(LOGIN_PAGE_URL),
  })
}
