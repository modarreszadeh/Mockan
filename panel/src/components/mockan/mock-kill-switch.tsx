/**
 * Header-level "Mocks on / off" (prompt §4.6): shows the count of enabled rules; turning off calls
 * `POST /me/rules/toggle-all` and confirms when more than one rule would be disabled. Mitigates the PRD risk
 * "developers forget enabled mocks".
 */
import { useId, useState } from "react"

import { useRules, useToggleAllRules } from "@/api/queries/rules"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"

import { ConfirmDialog } from "./confirm-dialog"

export function MockKillSwitch({ className }: { className?: string }) {
  const id = useId()
  const rules = useRules()
  const toggleAll = useToggleAllRules()
  const [confirming, setConfirming] = useState(false)

  if (rules.isPending) return <Skeleton className={cn("h-7 w-28", className)} />
  if (rules.isError) return null

  const total = rules.data.length
  const enabled = rules.data.filter((r) => r.isEnabled).length
  const on = enabled > 0

  const change = (next: boolean) => {
    if (!next && enabled > 1) setConfirming(true)
    else toggleAll.mutate({ isEnabled: next })
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Switch
        id={id}
        checked={on}
        disabled={total === 0 || toggleAll.isPending}
        onCheckedChange={change}
        aria-describedby={total > 0 ? `${id}-count` : undefined}
      />
      <Label htmlFor={id} className="type-caption whitespace-nowrap text-ink">
        {total === 0 ? "No mocks" : on ? "Mocks on" : "Mocks off"}
      </Label>
      {total > 0 ? (
        <span id={`${id}-count`} className="hidden font-mono text-[12px] text-muted-foreground tabular-nums sm:inline">
          <span className="sr-only">
            {pluralize(enabled, "rule")} enabled of {total}
          </span>
          <span aria-hidden>
            {enabled}/{total}
          </span>
        </span>
      ) : null}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Turn off all ${enabled} mocks?`}
        description="Every request will be proxied to the real backend. Your rules stay saved — turn them back on any time."
        confirmLabel="Turn mocks off"
        onConfirm={() => {
          setConfirming(false)
          toggleAll.mutate({ isEnabled: false })
        }}
      />
    </div>
  )
}
