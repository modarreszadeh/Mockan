import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-aligned actions, e.g. the page's one primary button. */
  actions?: ReactNode
  className?: string
}

/** Display `<h1>` (display-sm), one-line description in `body`, actions slot (prompt §4.6). */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0 space-y-1">
        <h1 className="type-display-sm text-ink">{title}</h1>
        {description ? <p className="text-body">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}
