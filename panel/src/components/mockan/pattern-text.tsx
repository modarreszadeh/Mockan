import type { MatchType } from "@/api/types"
import { cn } from "@/lib/utils"

export interface PatternTextProps {
  pattern: string
  matchType?: MatchType
  /** Truncate with an ellipsis; the full pattern is in `title`. */
  truncate?: boolean
  className?: string
}

const PARAM = /(\{\*?[A-Za-z_][A-Za-z0-9_]*\})/g

/** Mono pattern; `{param}` / `{*rest}` segments of Template patterns are highlighted in `primary-active`. */
export function PatternText({ pattern, matchType, truncate, className }: PatternTextProps) {
  const parts = matchType === "Template" ? pattern.split(PARAM) : [pattern]
  return (
    <code
      title={truncate ? pattern : undefined}
      className={cn("font-mono text-[13px] text-ink", truncate && "block truncate", className)}
    >
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <span key={index} className="text-primary-active">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </code>
  )
}
