import { lazy, Suspense, useMemo } from "react"

import { Button } from "@/components/ui/button"
import { formatBytes } from "@/lib/format"
import { byteLength, formatJsonProblem, jsonProblem, MAX_BODY_BYTES } from "@/lib/checks"
import { cn } from "@/lib/utils"

/** Monaco is lazy-loaded so it stays out of the initial bundle (prompt §8). */
const MonacoSurface = lazy(() => import("./monaco-surface"))

export interface JsonEditorProps {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  /** Accessible name, e.g. "Response body". */
  label: string
  /** A form or server error; shown instead of the live JSON check. */
  error?: string
  height?: number
  className?: string
}

/**
 * Monaco JSON editor with the dark token theme. Validates JSON on change and shows
 * `Line X, Col Y: message` below the editor (PR-06), a Format action, and a 1 MB size counter.
 */
export function JsonEditor({ id, value, onChange, onBlur, label, error, height = 280, className }: JsonEditorProps) {
  const problem = useMemo(() => (value.trim() ? jsonProblem(value) : null), [value])
  const size = useMemo(() => byteLength(value), [value])
  const message = error ?? (problem ? formatJsonProblem(problem) : undefined)
  const messageId = `${id}-message`

  const format = () => {
    if (problem || !value.trim()) return
    onChange(JSON.stringify(JSON.parse(value), null, 2))
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div
        className={cn(
          "overflow-hidden rounded-xl bg-surface-dark focus-within:ring-3 focus-within:ring-ring/40",
          message && "ring-2 ring-error/60",
        )}
      >
        <div className="flex items-center justify-between gap-2 bg-surface-dark-elevated px-3 py-1.5">
          <span className="type-overline text-on-dark-soft">JSON</span>
          <div className="flex items-center gap-2">
            <span
              className={cn("font-mono text-[12px]", size > MAX_BODY_BYTES ? "text-on-dark" : "text-on-dark-soft")}
              data-testid="json-size"
            >
              {formatBytes(size)} / 1 MB
            </span>
            <Button
              type="button"
              variant="onDark"
              size="sm"
              onClick={format}
              disabled={Boolean(problem) || !value.trim()}
            >
              Format
            </Button>
          </div>
        </div>
        <Suspense
          fallback={
            <div
              className="animate-pulse bg-surface-dark-soft"
              style={{ height }}
              role="status"
              aria-label="Loading editor"
            />
          }
        >
          <MonacoSurface
            id={id}
            value={value}
            onChange={onChange}
            onBlur={onBlur}
            label={label}
            height={height}
            describedBy={message ? messageId : undefined}
          />
        </Suspense>
      </div>
      {message ? (
        <p id={messageId} className="font-mono text-[13px] text-error" role="status">
          {message}
        </p>
      ) : null}
    </div>
  )
}
