/** The public share page's query (`GET /shared/rules/{token}`, S-3). No session: never redirects to sign-in. */
import { useQuery } from "@tanstack/react-query"

import { api } from "../client"
import type { SharedRule } from "../types"
import { sharedKeys } from "./keys"

export function useSharedRule(token: string | undefined) {
  return useQuery({
    queryKey: sharedKeys.rule(token ?? ""),
    queryFn: ({ signal }) => api.getPublic<SharedRule>(`/shared/rules/${encodeURIComponent(token ?? "")}`, signal),
    enabled: Boolean(token),
  })
}
