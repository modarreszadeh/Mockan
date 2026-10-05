/** `POST /me/test-route` (PR-13): what would happen to a request, decided by the Gateway's own code. */
import { useMutation } from "@tanstack/react-query"

import { api } from "../client"
import type { TestRouteRequest, TestRouteResult } from "../types"

export function useTestRoute() {
  return useMutation({
    mutationFn: (request: TestRouteRequest) => api.post<TestRouteResult>("/me/test-route", request),
  })
}
