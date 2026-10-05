/**
 * Scenario tabs (PR-11, OQ-P1): a rule's MockResponses as tabs. Exactly one is **active** (the Gateway serves it);
 * switching which one is active is its own action ("Make active"), separate from editing and saving a scenario.
 * Rendered inside a `<Tabs>` whose `value` is the selected scenario; the response form is its `TabsContent`.
 */
import { CopyIcon, Trash2Icon } from "lucide-react"

import type { MockResponse } from "@/api/types"
import { StatusCode } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { TabsList, TabsTrigger } from "@/components/ui/tabs"

export interface ScenarioBarProps {
  scenarios: MockResponse[]
  activeId: string | null
  selectedId: string
  onDuplicate: () => void
  onActivate: () => void
  onDelete: () => void
  /** A scenario request is in flight. */
  busy?: boolean
}

export function ActiveBadge() {
  return (
    <span className="inline-flex h-5 items-center gap-1.5 rounded-full bg-surface-card px-2 type-caption text-ink">
      <span aria-hidden className="size-2 rounded-full bg-accent-teal" />
      Active
    </span>
  )
}

export function ScenarioBar({
  scenarios,
  activeId,
  selectedId,
  onDuplicate,
  onActivate,
  onDelete,
  busy,
}: ScenarioBarProps) {
  const selectedIsLive = selectedId === activeId
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1 overflow-x-auto">
          <TabsList aria-label="Scenarios" className="h-auto w-max max-w-none flex-nowrap gap-1 p-1">
            {scenarios.map((scenario) => (
              <TabsTrigger key={scenario.id} value={scenario.id} className="h-9 flex-none gap-2 px-3">
                <span className="max-w-40 truncate font-mono text-[13px]">{scenario.name}</span>
                <StatusCode code={scenario.statusCode} />
                {scenario.id === activeId ? <ActiveBadge /> : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onDuplicate} disabled={busy}>
          <CopyIcon aria-hidden />
          Duplicate scenario
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {selectedIsLive ? (
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <ActiveBadge /> The Gateway serves this scenario.
          </p>
        ) : (
          <>
            <p className="text-[13px] text-muted-foreground">Not active. The Gateway serves another scenario.</p>
            <Button type="button" variant="outline" size="sm" onClick={onActivate} disabled={busy}>
              Make active
            </Button>
          </>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto text-error hover:text-error"
          onClick={onDelete}
          disabled={busy || scenarios.length < 2}
          title={scenarios.length < 2 ? "A rule needs at least one scenario." : undefined}
        >
          <Trash2Icon aria-hidden />
          Delete scenario
        </Button>
      </div>
    </div>
  )
}
