/**
 * SCR-04 Rules (PR-05, PR-08, PR-18, US-03, US-06): every MockRule in gateway precedence order (arch §7.2),
 * with search and filters (kept in the URL), optimistic toggles, duplicate and delete.
 */
import { CopyIcon, MoreHorizontalIcon, PencilIcon, PlusIcon, SlidersHorizontalIcon, Trash2Icon } from "lucide-react"
import { useMemo, useState, type MouseEvent, type ReactNode } from "react"
import { Link, useNavigate, useSearchParams } from "react-router"
import { toast } from "sonner"

import {
  activeResponse,
  useDeleteRule,
  useDuplicateRule,
  useRules,
  useToggleAllRules,
  useToggleRule,
} from "@/api/queries/rules"
import { useServices } from "@/api/queries/services"
import { HTTP_METHODS, MATCH_TYPES, type MockRule, type Service } from "@/api/types"
import {
  ConfirmDialog,
  EmptyState,
  MatchTypeBadge,
  MethodBadge,
  PageHeader,
  PatternText,
  ProblemAlert,
  StatusCode,
} from "@/components/mockan"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useIsMobile } from "@/hooks/use-mobile"
import { absoluteTime, pluralize, relativeTime } from "@/lib/format"
import { sortByPrecedence } from "@/lib/precedence"
import { cn } from "@/lib/utils"

const ALL = "all"
const NO_SERVICE = "none"

interface Filters {
  q: string
  state: string
  method: string
  type: string
  service: string
}

function useFilters() {
  const [params, setParams] = useSearchParams()
  const filters: Filters = {
    q: params.get("q") ?? "",
    state: params.get("state") ?? ALL,
    method: params.get("method") ?? ALL,
    type: params.get("type") ?? ALL,
    service: params.get("service") ?? ALL,
  }
  const set = (key: keyof Filters, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (!value || value === ALL) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  const clear = () => setParams({}, { replace: true })
  const active = Object.entries(filters).some(([k, v]) => (k === "q" ? v !== "" : v !== ALL))
  return { filters, set, clear, active }
}

function applyFilters(rules: MockRule[], f: Filters) {
  const q = f.q.trim().toLowerCase()
  return rules.filter(
    (r) =>
      (!q || r.name.toLowerCase().includes(q) || r.pattern.toLowerCase().includes(q)) &&
      (f.state === ALL || (f.state === "enabled" ? r.isEnabled : !r.isEnabled)) &&
      (f.method === ALL || r.method === f.method) &&
      (f.type === ALL || r.matchType === f.type) &&
      (f.service === ALL || (f.service === NO_SERVICE ? r.serviceId === null : r.serviceId === f.service)),
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
  className,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  children: ReactNode
  className?: string
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className={cn("w-full sm:w-40", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>{children}</SelectContent>
    </Select>
  )
}

const stop = (event: MouseEvent) => event.stopPropagation()

function RowMenu({ rule, onDelete }: { rule: MockRule; onDelete: () => void }) {
  const navigate = useNavigate()
  const duplicate = useDuplicateRule()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${rule.name}`} onClick={stop}>
          <MoreHorizontalIcon aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={stop}>
        <DropdownMenuItem onSelect={() => void navigate(`/rules/${rule.id}`)}>
          <PencilIcon aria-hidden />
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() =>
            duplicate.mutate(rule, {
              onSuccess: (copy) => toast.success(`Duplicated as “${copy.name}” — it's off until you enable it`),
              onError: () => toast.error("Couldn't duplicate the rule"),
            })
          }
        >
          <CopyIcon aria-hidden />
          Duplicate
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={onDelete}>
          <Trash2Icon aria-hidden />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RuleSwitch({ rule }: { rule: MockRule }) {
  const toggle = useToggleRule()
  return (
    <Switch
      checked={rule.isEnabled}
      onClick={stop}
      onCheckedChange={(isEnabled) => toggle.mutate({ ruleId: rule.id, isEnabled })}
      aria-label={`${rule.isEnabled ? "Disable" : "Enable"} ${rule.name}`}
    />
  )
}

function Scenario({ rule }: { rule: MockRule }) {
  const response = activeResponse(rule)
  if (!response) return <span className="text-muted-foreground">—</span>
  return (
    <span className="inline-flex items-center gap-2">
      <StatusCode code={response.statusCode} />
      <span className="font-mono text-[12px] text-muted-foreground">{response.name}</span>
    </span>
  )
}

function serviceName(services: Service[] | undefined, id: string | null) {
  if (id === null) return "Any"
  return services?.find((s) => s.id === id)?.name ?? "Unknown"
}

function RulesTable({
  rules,
  services,
  onDelete,
}: {
  rules: MockRule[]
  services: Service[] | undefined
  onDelete: (r: MockRule) => void
}) {
  const navigate = useNavigate()
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-14">
              <span className="sr-only">Enabled</span>
            </TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Method</TableHead>
            <TableHead>Match type</TableHead>
            <TableHead>Pattern</TableHead>
            <TableHead>Service</TableHead>
            <TableHead>Active scenario</TableHead>
            <TableHead className="text-right">Priority</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rules.map((rule) => (
            <TableRow
              key={rule.id}
              data-disabled={!rule.isEnabled || undefined}
              className={cn("cursor-pointer", !rule.isEnabled && "text-muted-foreground")}
              onClick={() => void navigate(`/rules/${rule.id}`)}
            >
              <TableCell>
                <RuleSwitch rule={rule} />
              </TableCell>
              <TableCell className="max-w-56">
                <Link
                  to={`/rules/${rule.id}`}
                  onClick={stop}
                  className={cn(
                    "block truncate rounded-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
                    rule.isEnabled ? "text-ink" : "text-muted-foreground",
                  )}
                >
                  {rule.name}
                </Link>
                {!rule.isEnabled ? <span className="text-[12px]">Off — proxied</span> : null}
              </TableCell>
              <TableCell>
                <MethodBadge method={rule.method} />
              </TableCell>
              <TableCell>
                <MatchTypeBadge matchType={rule.matchType} />
              </TableCell>
              <TableCell className="max-w-72">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block min-w-0">
                      <PatternText
                        pattern={rule.pattern}
                        matchType={rule.matchType}
                        truncate
                        className={cn(!rule.isEnabled && "text-muted-foreground")}
                      />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="font-mono">{rule.pattern}</TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell>{serviceName(services, rule.serviceId)}</TableCell>
              <TableCell>
                <Scenario rule={rule} />
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">{rule.priority}</TableCell>
              <TableCell>
                <time dateTime={rule.updatedAt} title={absoluteTime(rule.updatedAt)}>
                  {relativeTime(rule.updatedAt)}
                </time>
              </TableCell>
              <TableCell>
                <RowMenu rule={rule} onDelete={() => onDelete(rule)} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function RuleCards({
  rules,
  services,
  onDelete,
}: {
  rules: MockRule[]
  services: Service[] | undefined
  onDelete: (r: MockRule) => void
}) {
  return (
    <ul className="space-y-3">
      {rules.map((rule) => (
        <li
          key={rule.id}
          className={cn("space-y-3 rounded-xl border bg-canvas p-4", !rule.isEnabled && "text-muted-foreground")}
        >
          <div className="flex items-center gap-3">
            <RuleSwitch rule={rule} />
            <Link
              to={`/rules/${rule.id}`}
              className={cn(
                "min-w-0 flex-1 truncate font-medium",
                rule.isEnabled ? "text-ink" : "text-muted-foreground",
              )}
            >
              {rule.name}
            </Link>
            <RowMenu rule={rule} onDelete={() => onDelete(rule)} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MethodBadge method={rule.method} />
            <MatchTypeBadge matchType={rule.matchType} />
            <Scenario rule={rule} />
          </div>
          <div className="overflow-x-auto">
            <PatternText pattern={rule.pattern} matchType={rule.matchType} className="whitespace-nowrap" />
          </div>
          <p className="text-[13px]">
            {serviceName(services, rule.serviceId)} · priority {rule.priority} · {relativeTime(rule.updatedAt)}
          </p>
        </li>
      ))}
    </ul>
  )
}

function RulesSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border p-4" role="status" aria-busy="true" aria-label="Loading rules">
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function RulesPage() {
  const rules = useRules()
  const services = useServices()
  const toggleAll = useToggleAllRules()
  const deleteRule = useDeleteRule()
  const isMobile = useIsMobile()
  const { filters, set, clear, active } = useFilters()
  const [deleting, setDeleting] = useState<MockRule | null>(null)
  const [confirmDisableAll, setConfirmDisableAll] = useState(false)

  const sorted = useMemo(() => sortByPrecedence(rules.data ?? []), [rules.data])
  const visible = useMemo(() => applyFilters(sorted, filters), [sorted, filters])
  const enabledCount = sorted.filter((r) => r.isEnabled).length
  const hasRules = sorted.length > 0

  const header = (
    <PageHeader
      title="Mock rules"
      description="Requests that match an enabled rule get its mock response; everything else is proxied."
      actions={
        hasRules ? (
          <Button asChild>
            <Link to="/rules/new">
              <PlusIcon aria-hidden />
              New rule
            </Link>
          </Button>
        ) : null
      }
    />
  )

  if (rules.isError) {
    return (
      <div className="space-y-6">
        {header}
        <ProblemAlert error={rules.error} onRetry={() => void rules.refetch()} />
      </div>
    )
  }
  if (rules.isPending) {
    return (
      <div className="space-y-6">
        {header}
        <RulesSkeleton />
      </div>
    )
  }
  if (!hasRules) {
    return (
      <div className="space-y-6">
        {header}
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
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {header}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <Input
          type="search"
          aria-label="Search rules"
          placeholder="Search by name or pattern"
          value={filters.q}
          onChange={(e) => set("q", e.target.value)}
          className="lg:max-w-72"
        />
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <FilterSelect label="Filter by state" value={filters.state} onChange={(v) => set("state", v)}>
            <SelectItem value={ALL}>All states</SelectItem>
            <SelectItem value="enabled">Enabled</SelectItem>
            <SelectItem value="disabled">Disabled</SelectItem>
          </FilterSelect>
          <FilterSelect label="Filter by method" value={filters.method} onChange={(v) => set("method", v)}>
            <SelectItem value={ALL}>All methods</SelectItem>
            {HTTP_METHODS.map((m) => (
              <SelectItem key={m} value={m} className="font-mono">
                {m}
              </SelectItem>
            ))}
          </FilterSelect>
          <FilterSelect label="Filter by match type" value={filters.type} onChange={(v) => set("type", v)}>
            <SelectItem value={ALL}>All match types</SelectItem>
            {MATCH_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </FilterSelect>
          <FilterSelect label="Filter by Service" value={filters.service} onChange={(v) => set("service", v)}>
            <SelectItem value={ALL}>All Services</SelectItem>
            <SelectItem value={NO_SERVICE}>Any service (unscoped)</SelectItem>
            {services.data?.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </FilterSelect>
        </div>
        <Button
          variant="outline"
          className="lg:ml-auto"
          disabled={toggleAll.isPending}
          onClick={() =>
            enabledCount > 1 ? setConfirmDisableAll(true) : toggleAll.mutate({ isEnabled: enabledCount === 0 })
          }
        >
          {enabledCount > 0 ? "Disable all" : "Enable all"}
        </Button>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="type-caption text-muted-foreground">Sorted by match precedence</p>
        <p className="text-[13px] text-muted-foreground" aria-live="polite">
          {visible.length === sorted.length
            ? `${pluralize(sorted.length, "rule")} · ${enabledCount} enabled`
            : `${visible.length} of ${pluralize(sorted.length, "rule")}`}
        </p>
      </div>

      {visible.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-xl border p-6">
          <p className="text-body">No rules match these filters.</p>
          {active ? (
            <Button variant="outline" size="sm" onClick={clear}>
              Clear filters
            </Button>
          ) : null}
        </div>
      ) : isMobile ? (
        <RuleCards rules={visible} services={services.data} onDelete={setDeleting} />
      ) : (
        <RulesTable rules={visible} services={services.data} onDelete={setDeleting} />
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete “${deleting?.name ?? ""}”?`}
        description="The rule and its responses are deleted. Requests to this path will be proxied to the real backend again."
        confirmLabel="Delete rule"
        destructive
        pending={deleteRule.isPending}
        onConfirm={() =>
          deleting &&
          deleteRule.mutate(deleting.id, {
            onSuccess: () => {
              setDeleting(null)
              toast.success("Rule deleted — requests are proxied again in about 2 seconds")
            },
          })
        }
      />
      <ConfirmDialog
        open={confirmDisableAll}
        onOpenChange={setConfirmDisableAll}
        title={`Disable all ${enabledCount} rules?`}
        description="Every request will be proxied to the real backend. Your rules stay saved — enable them again any time."
        confirmLabel="Disable all"
        onConfirm={() => {
          setConfirmDisableAll(false)
          toggleAll.mutate({ isEnabled: false })
        }}
      />
    </div>
  )
}
