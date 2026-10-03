/**
 * SCR-03 Overview (PR-18, US-06, US-53, G4): greeting, base URL, stat tiles, active mocks with the shared toggle,
 * and the getting-started checklist. Data: GET /me, /me/rules, /services, /me/service-settings — no new endpoints.
 */
import { ArrowRightIcon, SlidersHorizontalIcon } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link } from "react-router"

import { useMe } from "@/api/queries/me"
import { activeResponse, useRules, useToggleRule } from "@/api/queries/rules"
import { selectedEnvironment, useServices, useServiceSettings } from "@/api/queries/services"
import type { MockRule } from "@/api/types"
import { BaseUrlCard, EmptyState, MethodBadge, PatternText, ProblemAlert, StatusCode } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { greeting, pluralize } from "@/lib/format"
import { sortByPrecedence } from "@/lib/precedence"
import { cn } from "@/lib/utils"

import { GettingStarted } from "./getting-started"

const MAX_ACTIVE = 8

function StatTile({
  label,
  value,
  note,
  link,
}: {
  label: string
  value: ReactNode
  note: ReactNode
  link?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1 rounded-xl bg-surface-card p-5">
      <p className="type-caption text-body">{label}</p>
      <p className="font-mono text-[28px] leading-tight text-ink tabular-nums">{value}</p>
      <div className="flex flex-wrap items-center justify-between gap-2 text-body">
        <span>{note}</span>
        {link}
      </div>
    </div>
  )
}

/** Links on surface-card use ink + underline (coral text fails contrast there). */
function TileLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="type-caption text-ink underline decoration-hairline underline-offset-4 hover:decoration-ink"
    >
      {children}
    </Link>
  )
}

function ActiveMocks({ rules }: { rules: MockRule[] }) {
  const toggle = useToggleRule()
  // Keep rules toggled here visible (dimmed) so the row doesn't jump away under the pointer.
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())
  const shown = sortByPrecedence(rules.filter((r) => r.isEnabled || touched.has(r.id))).slice(0, MAX_ACTIVE)

  return (
    <section aria-labelledby="active-mocks-title" className="rounded-xl border bg-canvas">
      <div className="flex items-center justify-between gap-2 border-b px-5 py-4">
        <h2 id="active-mocks-title" className="type-title-md text-ink">
          Active mocks
        </h2>
        <Button asChild variant="ghost" size="sm">
          <Link to="/rules">
            View all rules
            <ArrowRightIcon aria-hidden />
          </Link>
        </Button>
      </div>
      {shown.length === 0 ? (
        <p className="px-5 py-6 text-muted-foreground">
          All mocks are off — everything is proxied to the real backend.
        </p>
      ) : (
        <ul className="divide-y divide-hairline-soft">
          {shown.map((rule) => {
            const response = activeResponse(rule)
            return (
              <li
                key={rule.id}
                className={cn(
                  "flex items-center gap-3 px-5 py-3 hover:bg-surface-soft",
                  !rule.isEnabled && "text-muted-foreground",
                )}
              >
                <Switch
                  checked={rule.isEnabled}
                  aria-label={`${rule.isEnabled ? "Disable" : "Enable"} ${rule.name}`}
                  onCheckedChange={(isEnabled) => {
                    setTouched((prev) => new Set(prev).add(rule.id))
                    toggle.mutate({ ruleId: rule.id, isEnabled })
                  }}
                />
                <MethodBadge method={rule.method} />
                <Link
                  to={`/rules/${rule.id}`}
                  className="min-w-0 flex-1 rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                >
                  <PatternText
                    pattern={rule.pattern}
                    matchType={rule.matchType}
                    truncate
                    className={cn(!rule.isEnabled && "text-muted-foreground")}
                  />
                  <span className="block truncate text-[13px] text-muted-foreground">{rule.name}</span>
                </Link>
                {response ? <StatusCode code={response.statusCode} /> : null}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function OverviewSkeleton() {
  return (
    <div className="space-y-8" role="status" aria-busy="true" aria-label="Loading overview">
      <div className="space-y-2">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-5 w-96 max-w-full" />
      </div>
      <Skeleton className="h-36 w-full rounded-2xl" />
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-12">
        <Skeleton className="h-72 lg:col-span-8" />
        <Skeleton className="h-72 lg:col-span-4" />
      </div>
    </div>
  )
}

export function OverviewPage() {
  const me = useMe()
  const rules = useRules()
  const services = useServices()
  const settings = useServiceSettings()

  const queries = [rules, services, settings]
  const failed = queries.find((q) => q.isError)
  if (failed) {
    return (
      <ProblemAlert
        error={failed.error}
        onRetry={() => queries.filter((q) => q.isError).forEach((q) => void q.refetch())}
      />
    )
  }
  const developer = me.data
  const allRules = rules.data
  const catalog = services.data
  if (!developer?.slug || !allRules || !catalog || !settings.data) return <OverviewSkeleton />

  const slug = developer.slug
  const enabled = allRules.filter((r) => r.isEnabled).length
  const onDev = catalog.filter((s) => selectedEnvironment(s, settings.data)?.environment === "dev").length

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="type-display-md text-ink">
          {greeting()}, {developer.displayName}
        </h1>
        <p className="text-body">
          {enabled === 0
            ? "No mocks active · everything is proxied to the real backend."
            : `${pluralize(enabled, "mock")} active · everything else is proxied to the real backend.`}
        </p>
      </header>

      <BaseUrlCard slug={slug} />

      <div className="grid gap-4 md:grid-cols-3">
        <StatTile
          label="Active mocks"
          value={
            <>
              {enabled}
              <span className="text-body">/{allRules.length}</span>
            </>
          }
          note={allRules.length === 0 ? "No rules yet" : `${pluralize(allRules.length - enabled, "rule")} off`}
          link={<TileLink to="/rules">Rules</TileLink>}
        />
        <StatTile
          label="Services"
          value={catalog.length}
          note={`${onDev} on dev`}
          link={<TileLink to="/services">Environments</TileLink>}
        />
        <StatTile
          label="Allowed origins"
          value={developer.allowedOrigins.length}
          note={developer.allowedOrigins.length === 0 ? "Browser calls will fail CORS" : "For browser calls (CORS)"}
          link={<TileLink to="/settings">Settings</TileLink>}
        />
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <div className="min-w-0 lg:col-span-8">
          {allRules.length === 0 ? (
            <EmptyState
              icon={SlidersHorizontalIcon}
              title="Mock your first route"
              description="No rules yet — all traffic is proxied. Create your first mock."
              action={
                <Button asChild>
                  <Link to="/rules/new">Create your first mock</Link>
                </Button>
              }
            />
          ) : (
            <ActiveMocks rules={allRules} />
          )}
        </div>
        <div className="min-w-0 lg:col-span-4">
          <GettingStarted developerId={developer.id} hasSlug={Boolean(developer.slug)} hasRule={allRules.length > 0} />
        </div>
      </div>
    </div>
  )
}
