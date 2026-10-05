/** Request log (PR-12): history over REST, new entries over the `/hubs/request-log` WebSocket, "Mock this". */
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { api } from "../client"
import type { MockRule, RequestLogEntry, RequestLogFilters, RequestLogPage } from "../types"
import { logKeys, ruleKeys } from "./keys"

export const LOG_PAGE_SIZE = 50
/** Live entries kept in memory; older ones are still reachable through "Load more". */
const MAX_LIVE_ENTRIES = 500

export function useRequestLogHistory(filters: RequestLogFilters) {
  return useInfiniteQuery({
    queryKey: logKeys.list(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => {
      const params = new URLSearchParams({ limit: String(LOG_PAGE_SIZE) })
      if (pageParam) params.set("cursor", pageParam)
      if (filters.source) params.set("source", filters.source)
      if (filters.path?.trim()) params.set("path", filters.path.trim())
      return api.get<RequestLogPage>(`/me/request-logs?${params}`, signal)
    },
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  })
}

/** "Mock this" (FR-09): an Exact rule that answers the way the logged request was answered. */
export function useCreateRuleFromLog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (logId: number) => api.post<MockRule>(`/me/request-logs/${logId}/create-rule`),
    onSuccess: (rule) => {
      queryClient.setQueryData(ruleKeys.detail(rule.id), rule)
      void queryClient.invalidateQueries({ queryKey: ruleKeys.list() })
    },
  })
}

export type LiveStatus = "connecting" | "live" | "reconnecting"

/** `ws(s)://<this host>/hubs/request-log`: the hub lives at the Admin root, whatever the Panel's base path (OQ-03). */
export function hubUrl(location: Pick<Location, "protocol" | "host"> = window.location) {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/hubs/request-log`
}

const RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000, 10_000]

/**
 * Connects to the live hub while `enabled` and reports every entry logged after connecting. Reconnects with
 * backoff; a `401`/`403` handshake refusal just looks like a failed connection (the REST calls handle sign-in).
 * Entries are headers/bodies already masked by the server (NFR-07): this hook never logs them.
 */
export function useRequestLogSocket(enabled: boolean, onEntry: (entry: RequestLogEntry) => void) {
  const [status, setStatus] = useState<LiveStatus>("connecting")
  const handler = useRef(onEntry)
  useEffect(() => {
    handler.current = onEntry
  })

  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | undefined
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let closed = false

    const connect = () => {
      setStatus(attempt === 0 ? "connecting" : "reconnecting")
      socket = new WebSocket(hubUrl())
      socket.onopen = () => {
        attempt = 0
        setStatus("live")
      }
      socket.onmessage = (event) => {
        try {
          handler.current(JSON.parse(String(event.data)) as RequestLogEntry)
        } catch {
          // Not an entry: ignore it rather than break the feed.
        }
      }
      socket.onclose = () => {
        if (closed) return
        setStatus("reconnecting")
        timer = setTimeout(connect, RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)])
        attempt += 1
      }
    }
    connect()

    return () => {
      closed = true
      clearTimeout(timer)
      socket?.close()
    }
  }, [enabled])

  return enabled ? status : "connecting"
}

const matchesFilters = (entry: RequestLogEntry, { source, path }: RequestLogFilters) =>
  (!source || entry.source === source) &&
  (!path?.trim() || entry.path.toLowerCase().includes(path.trim().toLowerCase()))

export interface RequestLogFeed {
  entries: RequestLogEntry[]
  status: LiveStatus
  paused: boolean
  /** Entries that arrived while paused. */
  pendingCount: number
  setPaused: (paused: boolean) => void
  history: ReturnType<typeof useRequestLogHistory>
}

/**
 * History + live entries as one newest-first list: ids are unique and increase over time, so the two sources
 * are merged by id. Pausing holds new entries back (so rows don't move while you read) until you resume.
 */
export function useRequestLogFeed(filters: RequestLogFilters): RequestLogFeed {
  const history = useRequestLogHistory(filters)
  const [live, setLive] = useState<RequestLogEntry[]>([])
  const [paused, setPausedState] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const pausedRef = useRef(false)
  const heldRef = useRef<RequestLogEntry[]>([])

  const onEntry = useCallback((entry: RequestLogEntry) => {
    if (pausedRef.current) {
      heldRef.current = [entry, ...heldRef.current.filter((e) => e.id !== entry.id)]
      setPendingCount(heldRef.current.length)
      return
    }
    setLive((list) => [entry, ...list.filter((e) => e.id !== entry.id)].slice(0, MAX_LIVE_ENTRIES))
  }, [])
  const status = useRequestLogSocket(true, onEntry)

  const setPaused = useCallback((next: boolean) => {
    pausedRef.current = next
    setPausedState(next)
    if (next) return
    const pending = heldRef.current
    heldRef.current = []
    setPendingCount(0)
    if (pending.length === 0) return
    const ids = new Set(pending.map((e) => e.id))
    setLive((list) => [...pending, ...list.filter((e) => !ids.has(e.id))].slice(0, MAX_LIVE_ENTRIES))
  }, [])

  const entries = useMemo(() => {
    const byId = new Map<number, RequestLogEntry>()
    for (const entry of live) if (matchesFilters(entry, filters)) byId.set(entry.id, entry)
    for (const page of history.data?.pages ?? []) for (const entry of page.items) byId.set(entry.id, entry)
    return [...byId.values()].sort((a, b) => b.id - a.id)
  }, [live, history.data, filters])

  return { entries, status, paused, pendingCount, setPaused, history }
}
