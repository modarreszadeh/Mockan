import { cn } from "@/lib/utils"

export interface CodeBlockProps {
  code: string
  /** Accessible name for the scrollable region, e.g. "Response headers preview". */
  label: string
  className?: string
}

/** Read-only mono block on `surface-dark-soft` for headers/JSON previews. Scrolls horizontally, never wraps. */
export function CodeBlock({ code, label, className }: CodeBlockProps) {
  return (
    <pre
      tabIndex={0}
      role="region"
      aria-label={label}
      className={cn(
        "overflow-x-auto rounded-xl bg-surface-dark-soft p-4 type-code-sm whitespace-pre text-on-dark",
        className,
      )}
    >
      <code>{code}</code>
    </pre>
  )
}
