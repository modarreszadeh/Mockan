import { QueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Don't retry client errors (401 redirects, 403/404 render their own pages).
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  })
}
