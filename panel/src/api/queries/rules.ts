/** MockRule queries and mutations (`/me/rules*`, arch §10). */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, ApiError } from "../client"
import type {
  MockResponse,
  MockResponseInput,
  MockRule,
  MockRuleCreate,
  MockRuleUpdate,
  ImportMode,
  ImportResult,
  RulesExport,
  ToggleAllResult,
} from "../types"
import { ruleKeys } from "./keys"

export const LIVE_SOON = "Saved — live in about 2 seconds"

export function useRules() {
  return useQuery({
    queryKey: ruleKeys.list(),
    queryFn: ({ signal }) => api.get<MockRule[]>("/me/rules", signal),
  })
}

export function useRule(ruleId: string | undefined) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ruleKeys.detail(ruleId ?? ""),
    queryFn: ({ signal }) => api.get<MockRule>(`/me/rules/${ruleId}`, signal),
    enabled: Boolean(ruleId),
    initialData: () => queryClient.getQueryData<MockRule[]>(ruleKeys.list())?.find((r) => r.id === ruleId),
    initialDataUpdatedAt: () => queryClient.getQueryState(ruleKeys.list())?.dataUpdatedAt,
  })
}

/** The Scenario the Gateway serves for a rule (Phase 1 edits only this one, OQ-P1). */
export const activeResponse = (rule: MockRule): MockResponse | undefined =>
  rule.responses.find((r) => r.id === rule.activeResponseId) ?? rule.responses[0]

function patchRuleCaches(queryClient: QueryClient, update: (rule: MockRule) => MockRule) {
  queryClient.setQueryData<MockRule[]>(ruleKeys.list(), (rules) => rules?.map(update))
  queryClient.setQueriesData<MockRule>({ queryKey: [...ruleKeys.all, "detail"] }, (rule) =>
    rule ? update(rule) : rule,
  )
}

async function snapshotRuleCaches(queryClient: QueryClient) {
  await queryClient.cancelQueries({ queryKey: ruleKeys.all })
  return {
    list: queryClient.getQueryData<MockRule[]>(ruleKeys.list()),
    details: queryClient.getQueriesData<MockRule>({ queryKey: [...ruleKeys.all, "detail"] }),
  }
}

type RuleSnapshot = Awaited<ReturnType<typeof snapshotRuleCaches>>

function restoreRuleCaches(queryClient: QueryClient, snapshot: RuleSnapshot | undefined) {
  if (!snapshot) return
  queryClient.setQueryData(ruleKeys.list(), snapshot.list)
  for (const [key, data] of snapshot.details) queryClient.setQueryData(key, data)
}

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "Check your connection and try again."

/** Enable/disable one rule (PR-08). Optimistic, rolls back with a toast on error. Shared by Overview and Rules. */
export function useToggleRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ruleId, isEnabled }: { ruleId: string; isEnabled: boolean }) =>
      api.post<MockRule>(`/me/rules/${ruleId}/toggle`, { isEnabled }),
    onMutate: async ({ ruleId, isEnabled }) => {
      const snapshot = await snapshotRuleCaches(queryClient)
      patchRuleCaches(queryClient, (rule) => (rule.id === ruleId ? { ...rule, isEnabled } : rule))
      return snapshot
    },
    onError: (error, _vars, snapshot) => {
      restoreRuleCaches(queryClient, snapshot)
      toast.error("Couldn't change the rule", { description: errorMessage(error) })
    },
    onSuccess: () => toast.success(LIVE_SOON),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ruleKeys.all }),
  })
}

/** Enable/disable every rule (PR-08, FR-11). */
export function useToggleAllRules() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ isEnabled }: { isEnabled: boolean }) =>
      api.post<ToggleAllResult>("/me/rules/toggle-all", { isEnabled }),
    onMutate: async ({ isEnabled }) => {
      const snapshot = await snapshotRuleCaches(queryClient)
      patchRuleCaches(queryClient, (rule) => ({ ...rule, isEnabled }))
      return snapshot
    },
    onError: (error, _vars, snapshot) => {
      restoreRuleCaches(queryClient, snapshot)
      toast.error("Couldn't change your rules", { description: errorMessage(error) })
    },
    onSuccess: (_result, { isEnabled }) =>
      toast.success(
        isEnabled
          ? "All mocks on — live in about 2 seconds"
          : "All mocks off — everything is proxied in about 2 seconds",
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ruleKeys.all }),
  })
}

/** Prefix field errors from the response request so they land on `response.*` form fields. */
function prefixFieldErrors(error: unknown, prefix: string): never {
  if (error instanceof ApiError) {
    const prefixed = new ApiError(error.status, error.problem)
    for (const key of Object.keys(prefixed.fieldErrors)) {
      prefixed.fieldErrors[`${prefix}.${key}`] = prefixed.fieldErrors[key]!
      delete prefixed.fieldErrors[key]
    }
    throw prefixed
  }
  throw error
}

export interface SaveRuleInput {
  ruleId?: string
  rule: MockRuleUpdate
  response: MockResponseInput & { id?: string }
}

/**
 * Create (`POST /me/rules` with one response) or update (`PUT` rule, then `PUT`/`POST` the active
 * response). TODO(OQ-F5): payload shapes assumed. TODO(OQ-P1): Phase 2 adds scenario tabs.
 */
export function useSaveRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ ruleId, rule, response }: SaveRuleInput): Promise<MockRule> => {
      const { id: responseId, ...responseBody } = response
      if (!ruleId) {
        const body: MockRuleCreate = { ...rule, responses: [responseBody] }
        return api.post<MockRule>("/me/rules", body)
      }
      await api.put<MockRule>(`/me/rules/${ruleId}`, rule)
      try {
        if (responseId) await api.put<MockResponse>(`/me/rules/${ruleId}/responses/${responseId}`, responseBody)
        else await api.post<MockResponse>(`/me/rules/${ruleId}/responses`, responseBody)
      } catch (error) {
        prefixFieldErrors(error, "response")
      }
      return api.get<MockRule>(`/me/rules/${ruleId}`)
    },
    onSuccess: (rule) => {
      queryClient.setQueryData(ruleKeys.detail(rule.id), rule)
      void queryClient.invalidateQueries({ queryKey: ruleKeys.list() })
    },
  })
}

export function useDeleteRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ruleId: string) => api.delete(`/me/rules/${ruleId}`),
    onSuccess: (_void, ruleId) => {
      queryClient.setQueryData<MockRule[]>(ruleKeys.list(), (rules) => rules?.filter((r) => r.id !== ruleId))
      queryClient.removeQueries({ queryKey: ruleKeys.detail(ruleId) })
      void queryClient.invalidateQueries({ queryKey: ruleKeys.list() })
    },
  })
}

/** Duplicate is a client-side copy posted as a new rule (no dedicated endpoint, OQ-F5). */
export function useDuplicateRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (rule: MockRule) => {
      const body: MockRuleCreate = {
        serviceId: rule.serviceId,
        name: `${rule.name} (copy)`,
        method: rule.method,
        matchType: rule.matchType,
        pattern: rule.pattern,
        queryConditions: rule.queryConditions,
        headerConditions: rule.headerConditions,
        priority: rule.priority,
        isEnabled: false,
        responses: rule.responses.map(({ name, statusCode, headers, contentType, body, bodyMode, delayMs }) => ({
          name,
          statusCode,
          headers,
          contentType,
          body,
          bodyMode,
          delayMs,
        })),
      }
      return api.post<MockRule>("/me/rules", body)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ruleKeys.list() }),
  })
}

// ---- Scenarios (PR-11): a rule's MockResponses; exactly one is active ----

/** Make a scenario the one the Gateway serves. Idempotent. */
export function useActivateResponse(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (responseId: string) => api.post<MockRule>(`/me/rules/${ruleId}/responses/${responseId}/activate`),
    onSuccess: (rule) => {
      queryClient.setQueryData(ruleKeys.detail(rule.id), rule)
      void queryClient.invalidateQueries({ queryKey: ruleKeys.list() })
    },
  })
}

export function useAddResponse(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: MockResponseInput) => api.post<MockResponse>(`/me/rules/${ruleId}/responses`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ruleKeys.all }),
  })
}

/** Deleting the rule's last response is `409 last_response`; the editor disables the button before that. */
export function useDeleteResponse(ruleId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (responseId: string) => api.delete(`/me/rules/${ruleId}/responses/${responseId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ruleKeys.all }),
  })
}

// ---- Export / import (FR-12, PR-14) ----

export function useExportRules() {
  return useMutation({ mutationFn: () => api.get<RulesExport>("/me/rules/export") })
}

/** Validated server-side as a whole and written all-or-nothing; every problem comes back as `rules.<i>.<field>`. */
export function useImportRules() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, mode }: { file: unknown; mode: ImportMode }) =>
      api.post<ImportResult>(`/me/rules/import?mode=${mode}`, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ruleKeys.all }),
  })
}
