import type { ReactNode } from "react"

import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

/** Label + control + help + error, wired with ids for aria-describedby. */
export function Field({
  id,
  label,
  help,
  error,
  children,
  className,
}: {
  id: string
  label: ReactNode
  help?: ReactNode
  error?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id} className="type-caption text-ink">
        {label}
      </Label>
      {children}
      {help ? (
        <p id={`${id}-help`} className="text-[13px] text-muted-foreground">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-[13px] text-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export const describedBy = (id: string, opts: { help?: boolean; error?: boolean }) =>
  [opts.help ? `${id}-help` : null, opts.error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined

export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title: string
  description?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn("space-y-5 rounded-xl border bg-canvas p-5 sm:p-6", className)}>
      <div className="space-y-1">
        <h2 className="type-title-md text-ink">{title}</h2>
        {description ? <p className="text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}
