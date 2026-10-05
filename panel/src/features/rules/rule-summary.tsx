/**
 * Live summary (SCR-05): a plain-English sentence for the rule and a preview of the response headers the
 * Gateway will send, including `X-Mockan-Source: mock` (PR-09).
 */
import { useWatch, type Control } from "react-hook-form"

import type { HttpMethodOrAny, Service } from "@/api/types"
import { CodeBlock, MethodBadge, PatternText, StatusCode } from "@/components/mockan"
import { formatDelay } from "@/lib/format"
import { reasonPhrase } from "@/lib/http"
import type { KeyValueRow, RuleFormValues } from "@/lib/validation"

import { ANY_SERVICE } from "./rule-form-model"

function describeConditions(rows: KeyValueRow[], kind: "query parameter" | "header") {
  return rows
    .filter((r) => r.key.trim())
    .map((r) => (r.operator === "exists" ? `${kind} ${r.key} is present` : `${kind} ${r.key} = ${r.value}`))
}

export function RuleSummary({
  control,
  services,
  ruleId,
  isEnabled,
  activeScenarioName,
}: {
  control: Control<RuleFormValues>
  services: Service[] | undefined
  ruleId?: string
  /** The saved rule's state; `undefined` for a rule that doesn't exist yet. */
  isEnabled?: boolean
  /** Set when the scenario being edited is not the active one (PR-11). */
  activeScenarioName?: string
}) {
  const values = useWatch({ control }) as RuleFormValues
  const response = values.response
  const service = services?.find((s) => s.id === values.serviceId && values.serviceId !== ANY_SERVICE)
  const conditions = [
    ...describeConditions(values.queryConditions ?? [], "query parameter"),
    ...describeConditions(values.headerConditions ?? [], "header"),
  ]
  const status = Number.isFinite(response?.statusCode) ? response.statusCode : 200
  const delay = Number.isFinite(response?.delayMs) ? response.delayMs : 0
  const pattern = values.pattern?.trim() || "…"

  const headerLines = [
    `HTTP/1.1 ${status} ${reasonPhrase(status)}`.trimEnd(),
    `Content-Type: ${response?.contentType || "application/json"}`,
    ...(response?.headers ?? []).filter((h) => h.key.trim()).map((h) => `${h.key.trim()}: ${h.value}`),
    "X-Mockan-Source: mock",
    `X-Mockan-Rule-Id: ${ruleId ?? "<assigned when saved>"}`,
  ]

  return (
    <section aria-labelledby="summary-title" className="space-y-4 rounded-xl border bg-canvas p-5 sm:p-6">
      <h2 id="summary-title" className="type-title-md text-ink">
        Summary
      </h2>
      <p className="leading-7 text-body" data-testid="rule-sentence">
        {values.method === "ANY" ? (
          "Requests with any method"
        ) : (
          <>
            <MethodBadge method={values.method as HttpMethodOrAny} /> requests
          </>
        )}{" "}
        {values.matchType === "Exact"
          ? "to "
          : values.matchType === "Prefix"
            ? "to paths starting with "
            : values.matchType === "Template"
              ? "to paths like "
              : "to paths matching "}
        <PatternText
          pattern={pattern}
          matchType={values.matchType}
          className="rounded bg-surface-soft px-1 py-0.5 break-all"
        />
        {service ? (
          <>
            {" "}
            in <span className="font-medium text-ink">{service.name}</span>
          </>
        ) : null}
        {conditions.length ? <> when {conditions.join(" and ")}</> : null} return{" "}
        <strong className="font-medium text-ink">
          <StatusCode code={status} />
        </strong>
        {delay > 0 ? (
          <>
            {" "}
            after <strong className="font-medium text-ink">{formatDelay(delay)}</strong>
          </>
        ) : (
          " immediately"
        )}
        .
      </p>
      {isEnabled === false ? (
        <p className="text-[13px] text-ink" data-testid="disabled-note">
          This rule is disabled: it is skipped and matching requests are proxied to the real backend.
        </p>
      ) : null}
      {activeScenarioName ? (
        <p className="text-[13px] text-ink" data-testid="not-active-note">
          This scenario isn't active: when the rule matches, requests get{" "}
          <span className="font-mono">{activeScenarioName}</span> until you make this one active.
        </p>
      ) : null}
      <p className="text-[13px] text-muted-foreground">
        Matched against the path after your slug. Requests that don't match are proxied to the real backend.
      </p>
      <div className="space-y-1.5">
        <p className="type-caption text-ink">Response headers</p>
        <CodeBlock label="Response headers preview" code={headerLines.join("\n")} language="http" />
      </div>
    </section>
  )
}
