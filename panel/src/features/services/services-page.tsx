/**
 * SCR-06 Services (PR-04, US-07): the shared catalog with a per-Developer environment choice. Changing the
 * environment saves immediately (optimistic). Non-admins see no catalog edit controls (PR-10).
 */
import { ServerIcon } from "lucide-react"
import { Link } from "react-router"
import { toast } from "sonner"

import { useMe } from "@/api/queries/me"
import { selectedEnvironment, useServices, useServiceSettings, useUpdateServiceSettings } from "@/api/queries/services"
import type { DeveloperServiceSetting, Service } from "@/api/types"
import { EmptyState, EnvBadge, PageHeader, ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useIsMobile } from "@/hooks/use-mobile"

function EnvironmentPicker({
  service,
  settings,
  onChange,
}: {
  service: Service
  settings: DeveloperServiceSetting[]
  onChange: (environmentId: string) => void
}) {
  const current = selectedEnvironment(service, settings)
  if (!current) return <span className="text-muted-foreground">No environments</span>
  const isOverride = current.environment !== service.defaultEnvironment

  if (service.environments.length === 1) {
    return <EnvBadge environment={current.environment} isDefault={!isOverride} />
  }
  return (
    <Select value={current.id} onValueChange={onChange}>
      <SelectTrigger size="sm" className="w-40" aria-label={`Environment for ${service.name}`}>
        <SelectValue>
          <span className="flex items-center gap-1.5">
            {isOverride ? <span aria-hidden className="size-2 rounded-full bg-accent-amber" /> : null}
            <span className="font-mono">{current.environment}</span>
            {!isOverride ? <span className="text-muted-foreground">· default</span> : null}
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {service.environments.map((env) => (
          <SelectItem key={env.id} value={env.id}>
            <span className="font-mono">{env.environment}</span>
            {env.environment === service.defaultEnvironment ? (
              <span className="text-muted-foreground">· default</span>
            ) : null}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function UpstreamUrl({ url }: { url: string | undefined }) {
  if (!url) return <span className="text-muted-foreground">—</span>
  return (
    <code title={url} className="block max-w-72 truncate font-mono text-[13px] text-body">
      {url}
    </code>
  )
}

function ServicesSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border p-4" role="status" aria-busy="true" aria-label="Loading Services">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function ServicesPage() {
  const me = useMe()
  const services = useServices()
  const settings = useServiceSettings()
  const update = useUpdateServiceSettings()
  const isMobile = useIsMobile()
  const isAdmin = Boolean(me.data?.isAdmin)

  const choose = (service: Service, environmentId: string) => {
    const current = settings.data ?? []
    const env = service.environments.find((e) => e.id === environmentId)
    if (!env) return
    const others = current.filter((s) => s.serviceId !== service.id)
    // Absent row = Service default (arch §8), so choosing the default removes the override.
    const next =
      env.environment === service.defaultEnvironment
        ? others
        : [...others, { serviceId: service.id, serviceEnvironmentId: env.id }]
    update.mutate(next, {
      onSuccess: () => toast.success(`${service.name} now proxies to ${env.environment} — live in about 2 seconds`),
    })
  }

  const header = (
    <PageHeader
      title="Services"
      description="Pick the backend environment each Service proxies to. Your choice only affects your workspace."
      actions={
        isAdmin ? (
          <Button asChild variant="outline">
            <Link to="/admin/services">Manage catalog</Link>
          </Button>
        ) : null
      }
    />
  )

  const failed = [services, settings].find((q) => q.isError)
  const catalog = services.data
  const chosen = settings.data
  let body
  if (failed) {
    body = <ProblemAlert error={failed.error} onRetry={() => [services, settings].forEach((q) => void q.refetch())} />
  } else if (!catalog || !chosen) {
    body = <ServicesSkeleton />
  } else if (catalog.length === 0) {
    body = (
      <EmptyState
        icon={ServerIcon}
        title="No Services in the catalog yet"
        description={
          isAdmin
            ? "Register a backend Service with its path prefix and dev/stage base URLs so requests can be proxied."
            : "Ask a Mockan admin to register your backend Services. Until then, requests can't be proxied."
        }
        action={
          isAdmin ? (
            <Button asChild>
              <Link to="/admin/services">Add a Service</Link>
            </Button>
          ) : null
        }
      />
    )
  } else if (isMobile) {
    body = (
      <ul className="space-y-3">
        {catalog.map((service) => {
          const env = selectedEnvironment(service, chosen)
          return (
            <li key={service.id} className="space-y-3 rounded-xl border bg-canvas p-4">
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="type-title-sm text-ink">{service.name}</h2>
                <code className="font-mono text-[13px] text-body">{service.pathPrefix}</code>
              </div>
              <EnvironmentPicker service={service} settings={chosen} onChange={(id) => choose(service, id)} />
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
                <dt className="text-muted-foreground">Strip prefix</dt>
                <dd>{service.stripPrefix ? "Yes" : "No"}</dd>
                <dt className="text-muted-foreground">Upstream</dt>
                <dd className="min-w-0">
                  <UpstreamUrl url={env?.baseUrl} />
                </dd>
              </dl>
            </li>
          )
        })}
      </ul>
    )
  } else {
    body = (
      <div className="overflow-hidden rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Service</TableHead>
              <TableHead>Path prefix</TableHead>
              <TableHead>Strip prefix</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Upstream base URL</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {catalog.map((service) => (
              <TableRow key={service.id}>
                <TableCell className="font-medium text-ink">{service.name}</TableCell>
                <TableCell>
                  <code className="font-mono text-[13px]">{service.pathPrefix}</code>
                </TableCell>
                <TableCell>{service.stripPrefix ? "Yes" : "No"}</TableCell>
                <TableCell>
                  <EnvironmentPicker service={service} settings={chosen} onChange={(id) => choose(service, id)} />
                </TableCell>
                <TableCell>
                  <UpstreamUrl url={selectedEnvironment(service, chosen)?.baseUrl} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {header}
      {body}
      {services.data && services.data.length > 0 ? (
        <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <span aria-hidden className="size-2 rounded-full bg-accent-amber" />
          Amber dot: you're using an environment other than the Service default.
        </p>
      ) : null}
    </div>
  )
}
