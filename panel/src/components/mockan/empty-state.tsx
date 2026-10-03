import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: ReactNode
  /** One primary action. */
  action?: ReactNode
  className?: string
}

/** `feature-card` recipe: `surface-card`, 12 px radius, 32 px padding. Secondary text uses `body` (contrast rule). */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-start gap-3 rounded-xl bg-surface-card p-8", className)}>
      <Icon aria-hidden className="size-5 text-ink" strokeWidth={1.75} />
      <h2 className="type-title-md text-ink">{title}</h2>
      <p className="max-w-prose text-body">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}
