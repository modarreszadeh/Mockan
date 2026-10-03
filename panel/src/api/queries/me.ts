/** `GET/PUT /me` and logout. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, API_BASE } from "../client"
import type { Developer, DeveloperUpdate } from "../types"
import { meKeys } from "./keys"

export const fetchMe = (signal?: AbortSignal) => api.get<Developer>("/me", signal)

export function useMe() {
  return useQuery({ queryKey: meKeys.all, queryFn: ({ signal }) => fetchMe(signal), staleTime: 60_000 })
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
    onSettled: () => window.location.assign(`${API_BASE}/auth/login`),
  })
}
