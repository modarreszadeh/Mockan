/**
 * SCR-09 Live log (PR-12, FR-09, US-20): the Developer's recent requests, newest first. History comes from
 * `GET /me/request-logs`, new entries arrive over the `/hubs/request-log` WebSocket. Filters live in the URL.
 */
import { PauseIcon, PlayIcon, ScrollTextIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router"

import { useRequestLogFeed, type LiveStatus } from "@/api/queries/logs"
import { useMe, usePublicBaseUrl } from "@/api/queries/me"
import { useServices } from "@/api/queries/services"
import type { RequestLogEntry, RequestLogFilters, RequestSource } from "@/api/types"
import { EmptyState, MethodBadge, PageHeader, ProblemAlert, SourceBadge, StatusCode } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { useIsMobile } from "@/hooks/use-mobile"
import { developerBaseUrl, logTime } from "@/lib/format"
import { cn } from "@/lib/utils"

import { LogDetailsModal } from "./log-details-modal"

const ALL = "all"
const SOURCES: readonly RequestSource[] = ["Proxied", "Mocked", "Error"]

function useLogFilters() {
  const [params, setParams] = useSearchParams()
  const rawSource = params.get("source")
  const source = SOURCES.find((s) => s === rawSource)
  const path = params.get("path") ?? ""
  const set = (key: "source" | "path", value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (!value || value === ALL) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  const filters: RequestLogFilters = useMemo(() => ({ source, path: path || undefined }), [source, path])
  return { filters, set, active: Boolean(source || path) }
}

const STATUS_COPY: Record<LiveStatus, { label: string; dot: string }> = {
  connecting: { label: "Connecting…", dot: "bg-muted-foreground" },
  live: { label: "Live", dot: "bg-accent-teal" },
  reconnecting: { label: "Reconnecting…", dot: "bg-warning" },
}

function LiveIndicator({ status, paused }: { status: LiveStatus; paused: boolean }) {
  const { label, dot } = paused ? { label: "Paused", dot: "bg-muted-foreground" } : STATUS_COPY[status]
  return (
    <span
      role="status"
      className="inline-flex h-9 items-center gap-2 rounded-full bg-surface-card px-3 type-caption text-ink"
    >
      <span aria-hidden className={cn("size-2 rounded-full", dot)} />
      {label}
    </span>
  )
}

function LogTable({ entries, onOpen }: { entries: RequestLogEntry[]; onOpen: (entry: RequestLogEntry) => void }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-28">Time</TableHead>
            <TableHead>Method</TableHead>
            <TableHead>Path</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Duration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id} className="cursor-pointer" onClick={() => onOpen(entry)}>
              <TableCell className="font-mono text-[13px] text-muted-foreground tabular-nums">
                <time dateTime={entry.timestamp}>{logTime(entry.timestamp)}</time>
              </TableCell>
              <TableCell>
                <MethodBadge method={entry.method} />
              </TableCell>
              <TableCell className="max-w-96">
                <button
                  type="button"
                  className="block w-full truncate rounded-sm text-left font-mono text-[13px] text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                  onClick={(event) => {
                    event.stopPropagation()
                    onOpen(entry)
                  }}
                  aria-label={`Details of ${entry.method} ${entry.path}`}
                >
                  {entry.path}
                  {entry.query ? <span className="text-muted-foreground">?{entry.query}</span> : null}
                </button>
              </TableCell>
              <TableCell>
                <SourceBadge source={entry.source} />
              </TableCell>
              <TableCell>
                <StatusCode code={entry.statusCode} />
              </TableCell>
              <TableCell className="text-right font-mono text-[13px] tabular-nums">{entry.durationMs} ms</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function LogCards({ entries, onOpen }: { entries: RequestLogEntry[]; onOpen: (entry: RequestLogEntry) => void }) {
  return (
    <ul className="space-y-3">
      {entries.map((entry) => (
        <li key={entry.id}>
          <button
            type="button"
            onClick={() => onOpen(entry)}
            aria-label={`Details of ${entry.method} ${entry.path}`}
            className="w-full space-y-2 rounded-xl border bg-canvas p-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
          >
            <span className="flex flex-wrap items-center gap-2">
              <MethodBadge method={entry.method} />
              <SourceBadge source={entry.source} />
              <StatusCode code={entry.statusCode} />
            </span>
            <span className="block truncate font-mono text-[13px] text-ink">{entry.path}</span>
            <span className="block text-[13px] text-muted-foreground">
              {logTime(entry.timestamp)} · {entry.durationMs} ms
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function LogSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border p-4" role="status" aria-busy="true" aria-label="Loading requests">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function LogsPage() {
  const { filters, set, active } = useLogFilters()
  const [pathInput, setPathInput] = useState(filters.path ?? "")
  const debouncedPath = useDebouncedValue(pathInput)
  useEffect(() => {
    if (debouncedPath !== (filters.path ?? "")) set("path", debouncedPath.trim())
    // `set` and `filters.path` only change through this effect's own writes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedPath])

  const feed = useRequestLogFeed(filters)
  const services = useServices()
  const me = useMe()
  const publicBaseUrl = usePublicBaseUrl()
  const isMobile = useIsMobile()
  const [opened, setOpened] = useState<RequestLogEntry | null>(null)
  const { entries, history } = feed

  const header = (
    <PageHeader
      title="Live log"
      description="Requests that went through your base URL, newest first. Kept for 7 days."
      actions={
        <>
          <LiveIndicator status={feed.status} paused={feed.paused} />
          <Button variant="outline" onClick={() => feed.setPaused(!feed.paused)}>
            {feed.paused ? <PlayIcon aria-hidden /> : <PauseIcon aria-hidden />}
            {feed.paused ? (feed.pendingCount > 0 ? `Resume (${feed.pendingCount} new)` : "Resume") : "Pause"}
          </Button>
        </>
      }
    />
  )

  const toolbar = (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <Input
        type="search"
        aria-label="Filter by path"
        placeholder="Filter by path, e.g. /orders"
        className="font-mono sm:w-80"
        value={pathInput}
        onChange={(event) => setPathInput(event.target.value)}
      />
      <Select value={filters.source ?? ALL} onValueChange={(value) => set("source", value)}>
        <SelectTrigger aria-label="Source" className="w-full sm:w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All sources</SelectItem>
          {SOURCES.map((source) => (
            <SelectItem key={source} value={source}>
              {source}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  let body
  if (history.isError && entries.length === 0) {
    body = <ProblemAlert error={history.error} onRetry={() => void history.refetch()} />
  } else if (history.isPending && entries.length === 0) {
    body = <LogSkeleton />
  } else if (entries.length === 0) {
    body = active ? (
      <EmptyState
        icon={ScrollTextIcon}
        title="No requests match"
        description="Nothing in the log matches these filters. Clear them to see everything."
        action={
          <Button
            variant="outline"
            onClick={() => {
              setPathInput("")
              set("path", "")
              set("source", ALL)
            }}
          >
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={ScrollTextIcon}
        title="No requests yet"
        description={
          <>
            Send a request to{" "}
            <code className="font-mono text-ink">
              {me.data?.slug ? developerBaseUrl(publicBaseUrl, me.data.slug) : publicBaseUrl}
            </code>{" "}
            and it shows up here as it happens.
          </>
        }
      />
    )
  } else {
    body = (
      <>
        {isMobile ? (
          <LogCards entries={entries} onOpen={setOpened} />
        ) : (
          <LogTable entries={entries} onOpen={setOpened} />
        )}
        {history.hasNextPage ? (
          <div className="flex justify-center">
            <Button
              variant="outline"
              onClick={() => void history.fetchNextPage()}
              disabled={history.isFetchingNextPage}
            >
              {history.isFetchingNextPage ? "Loading…" : "Load older requests"}
            </Button>
          </div>
        ) : null}
      </>
    )
  }

  return (
    <div className="space-y-6">
      {header}
      {toolbar}
      {history.isError && entries.length > 0 ? (
        <ProblemAlert error={history.error} onRetry={() => void history.refetch()} />
      ) : null}
      {body}
      <LogDetailsModal entry={opened} services={services.data} onClose={() => setOpened(null)} />
    </div>
  )
}
