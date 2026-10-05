/**
 * Status language badges (prompt §4.5). Every badge carries text — colour is never the only signal.
 * Contrast note: `muted` and `error` text fail 4.5:1 on `surface-card`, so `ANY` and `DELETE` pills use
 * the canvas fill with a hairline border instead (see docs/frontend/design-tokens.md).
 */
import type { EnvironmentName, HttpMethodOrAny, MatchType, RequestSource } from "@/api/types"
import { cn } from "@/lib/utils"

const pill = "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 whitespace-nowrap"

/** `method` is a string because a logged request can use any verb; the known ones get their tones. */
export function MethodBadge({ method, className }: { method: HttpMethodOrAny | (string & {}); className?: string }) {
  const tone =
    method === "DELETE"
      ? "border border-hairline bg-canvas text-error"
      : method === "ANY"
        ? "border border-hairline bg-canvas text-muted-foreground"
        : "bg-surface-card text-ink"
  return (
    <span className={cn(pill, "font-mono text-[12px] font-medium tracking-wide uppercase", tone, className)}>
      {method}
    </span>
  )
}

export function MatchTypeBadge({ matchType, className }: { matchType: MatchType; className?: string }) {
  return (
    <span className={cn(pill, "border border-hairline bg-canvas type-caption text-body", className)}>{matchType}</span>
  )
}

const dot = "size-2 shrink-0 rounded-full"

const SOURCE_DOT: Record<RequestSource, string> = {
  Mocked: "bg-accent-amber",
  Proxied: "bg-accent-teal",
  Error: "bg-error",
}

export function SourceBadge({ source, className }: { source: RequestSource; className?: string }) {
  return (
    <span className={cn(pill, "bg-surface-card type-caption text-ink", className)}>
      <span aria-hidden className={cn(dot, SOURCE_DOT[source])} />
      {source}
    </span>
  )
}

/** Mono status code; 4xx gets a `warning` dot, 5xx an `error` dot (prompt §4.5). */
export function StatusCode({ code, className }: { code: number; className?: string }) {
  const family = Math.floor(code / 100)
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[13px] tabular-nums",
        family === 3 ? "text-body" : "text-ink",
        className,
      )}
    >
      {family === 4 ? <span aria-hidden className={cn(dot, "bg-warning")} /> : null}
      {family === 5 ? <span aria-hidden className={cn(dot, "bg-error")} /> : null}
      {code}
    </span>
  )
}

export interface EnvBadgeProps {
  environment: EnvironmentName
  /** This is the Service's default environment. */
  isDefault?: boolean
  /** The Developer picked an environment other than the Service default. */
  isOverride?: boolean
  className?: string
}

export function EnvBadge({ environment, isDefault, isOverride, className }: EnvBadgeProps) {
  return (
    <span className={cn(pill, "bg-surface-card type-caption text-ink", className)}>
      {isOverride ? <span aria-hidden className={cn(dot, "bg-accent-amber")} /> : null}
      <span className="font-mono">{environment}</span>
      {isDefault ? <span className="text-body">· default</span> : null}
      {isOverride ? <span className="sr-only">(not the Service default)</span> : null}
    </span>
  )
}

/** `badge-coral` — only for Phase-2 / Beta tags behind a flag. */
export function CoralBadge({ children, className }: { children: string; className?: string }) {
  return <span className={cn(pill, "bg-primary type-overline text-primary-foreground", className)}>{children}</span>
}
