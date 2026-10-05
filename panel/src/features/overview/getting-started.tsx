/**
 * Getting-started checklist (SCR-03). "Claim slug" and "Create your first mock" are derived; the other two are
 * manual ticks kept in localStorage (per Developer). The card hides once everything is ticked.
 */
import { useState, type ReactNode } from "react"

import { Checkbox } from "@/components/ui/checkbox"

type ManualStep = "env" | "header"

const storageKey = (developerId: string) => `mockan.checklist.${developerId}`

function readTicks(developerId: string): ManualStep[] {
  try {
    const raw = localStorage.getItem(storageKey(developerId))
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((s): s is ManualStep => s === "env" || s === "header") : []
  } catch {
    return []
  }
}

function writeTicks(developerId: string, ticks: ManualStep[]) {
  try {
    localStorage.setItem(storageKey(developerId), JSON.stringify(ticks))
  } catch {
    // Storage blocked: ticks last for this page view only.
  }
}

interface Step {
  id: string
  label: ReactNode
  done: boolean
  manual?: ManualStep
}

export function GettingStarted({
  developerId,
  hasSlug,
  hasRule,
}: {
  developerId: string
  hasSlug: boolean
  hasRule: boolean
}) {
  const [ticks, setTicks] = useState<ManualStep[]>(() => readTicks(developerId))

  const steps: Step[] = [
    { id: "slug", label: "Claim your slug", done: hasSlug },
    {
      id: "env",
      label: (
        <>
          Point <code className="font-mono text-[13px]">.env</code> at Mockan
        </>
      ),
      done: ticks.includes("env"),
      manual: "env",
    },
    { id: "rule", label: "Create your first mock", done: hasRule },
    {
      id: "header",
      label: (
        <>
          Check <code className="font-mono text-[13px]">X-Mockan-Source</code> in DevTools
        </>
      ),
      done: ticks.includes("header"),
      manual: "header",
    },
  ]
  if (steps.every((s) => s.done)) return null

  const toggle = (step: ManualStep, checked: boolean) => {
    const next = checked ? [...new Set([...ticks, step])] : ticks.filter((t) => t !== step)
    setTicks(next)
    writeTicks(developerId, next)
  }

  const doneCount = steps.filter((s) => s.done).length

  return (
    <section aria-labelledby="getting-started-title" className="space-y-4 rounded-xl bg-surface-card p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="getting-started-title" className="type-title-md text-ink">
          Getting started
        </h2>
        <span className="type-caption text-body">
          {doneCount} of {steps.length}
        </span>
      </div>
      <ul className="space-y-3">
        {steps.map((step) => {
          const id = `checklist-${step.id}`
          return (
            <li key={step.id} className="flex items-start gap-3">
              <Checkbox
                id={id}
                className="mt-0.5 bg-canvas data-checked:border-ink data-checked:bg-ink data-checked:text-on-dark"
                checked={step.done}
                disabled={!step.manual}
                onCheckedChange={(checked) => step.manual && toggle(step.manual, checked === true)}
              />
              <label htmlFor={id} className={step.done ? "text-body line-through decoration-body/50" : "text-ink"}>
                {step.label}
                {!step.manual ? <span className="sr-only"> (ticked automatically)</span> : null}
              </label>
            </li>
          )
        })}
      </ul>
      <p className="text-[13px] text-body">
        Mocked responses carry <code className="font-mono">X-Mockan-Source: mock</code>; proxied ones say{" "}
        <code className="font-mono">proxy</code>.
      </p>
    </section>
  )
}
