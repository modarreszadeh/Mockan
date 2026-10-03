/**
 * SCR-07 Service catalog (admin; PR-10, PR-15, US-30, US-31): the shared list of backend Services with their
 * dev/stage base URLs. Non-admins never get here (AdminGate renders a 403 page).
 */
import { BlocksIcon, MoreHorizontalIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react"
import { useState, type MouseEvent } from "react"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { useDeleteService, useServices } from "@/api/queries/services"
import type { Service } from "@/api/types"
import { ConfirmDialog, EmptyState, EnvBadge, PageHeader, ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useIsMobile } from "@/hooks/use-mobile"

import { ServiceSheet } from "./service-sheet"

const stop = (event: MouseEvent) => event.stopPropagation()

function Environments({ service }: { service: Service }) {
  if (service.environments.length === 0) return <span className="text-error">No environments</span>
  return (
    <ul className="space-y-1">
      {service.environments.map((env) => (
        <li key={env.id} className="flex min-w-0 items-center gap-2">
          <EnvBadge environment={env.environment} isDefault={env.environment === service.defaultEnvironment} />
          <code title={env.baseUrl} className="truncate font-mono text-[13px] text-body">
            {env.baseUrl}
          </code>
        </li>
      ))}
    </ul>
  )
}

function ServiceMenu({ service, onEdit, onDelete }: { service: Service; onEdit: () => void; onDelete: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${service.name}`} onClick={stop}>
          <MoreHorizontalIcon aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={stop}>
        <DropdownMenuItem onSelect={onEdit}>
          <PencilIcon aria-hidden />
          Edit
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

export function ServiceCatalogPage() {
  const services = useServices()
  const deleteService = useDeleteService()
  const [editing, setEditing] = useState<{ service: Service | null } | null>(null)
  const [deleting, setDeleting] = useState<Service | null>(null)
  const isMobile = useIsMobile()
  const hasServices = (services.data?.length ?? 0) > 0

  const header = (
    <PageHeader
      title="Service catalog"
      description="Register backend Services and their dev/stage base URLs. Developers pick the environment."
      actions={
        hasServices ? (
          <Button onClick={() => setEditing({ service: null })}>
            <PlusIcon aria-hidden />
            Add Service
          </Button>
        ) : null
      }
    />
  )

  let body
  if (services.isError) body = <ProblemAlert error={services.error} onRetry={() => void services.refetch()} />
  else if (services.isPending)
    body = (
      <div className="space-y-2 rounded-xl border p-4" role="status" aria-busy="true" aria-label="Loading Services">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  else if (!hasServices)
    body = (
      <EmptyState
        icon={BlocksIcon}
        title="No Services yet"
        description="Add the backend Services frontend apps call, with their path prefix and allowlisted dev/stage base URLs."
        action={<Button onClick={() => setEditing({ service: null })}>Add Service</Button>}
      />
    )
  else if (isMobile)
    body = (
      <ul className="space-y-3">
        {services.data.map((service) => (
          <li key={service.id} className="space-y-3 rounded-xl border bg-canvas p-4">
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left font-mono font-medium text-ink"
                onClick={() => setEditing({ service })}
              >
                {service.name}
              </button>
              <code className="font-mono text-[13px] text-body">{service.pathPrefix}</code>
              <ServiceMenu
                service={service}
                onEdit={() => setEditing({ service })}
                onDelete={() => setDeleting(service)}
              />
            </div>
            <Environments service={service} />
            <p className="text-[13px] text-muted-foreground">
              Strip prefix {service.stripPrefix ? "yes" : "no"} · rewrite origin {service.rewriteOrigin ? "yes" : "no"}
            </p>
          </li>
        ))}
      </ul>
    )
  else
    body = (
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Name</TableHead>
              <TableHead>Path prefix</TableHead>
              <TableHead>Strip prefix</TableHead>
              <TableHead>Rewrite origin</TableHead>
              <TableHead>Environments</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {services.data.map((service) => (
              <TableRow key={service.id} className="cursor-pointer" onClick={() => setEditing({ service })}>
                <TableCell className="font-mono font-medium text-ink">{service.name}</TableCell>
                <TableCell>
                  <code className="font-mono text-[13px]">{service.pathPrefix}</code>
                </TableCell>
                <TableCell>{service.stripPrefix ? "Yes" : "No"}</TableCell>
                <TableCell>{service.rewriteOrigin ? "Yes" : "No"}</TableCell>
                <TableCell className="max-w-96">
                  <Environments service={service} />
                </TableCell>
                <TableCell>
                  <ServiceMenu
                    service={service}
                    onEdit={() => setEditing({ service })}
                    onDelete={() => setDeleting(service)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    )

  return (
    <div className="space-y-6">
      {header}
      {body}
      <ServiceSheet
        open={editing !== null}
        service={editing?.service ?? null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete Service “${deleting?.name ?? ""}”?`}
        description={
          <>
            Requests under <code className="font-mono text-ink">{deleting?.pathPrefix}</code> will no longer be proxied
            for any Developer (<code className="font-mono text-ink">service_not_resolved</code>). Rules scoped to it
            become unscoped.
          </>
        }
        confirmLabel={`Delete ${deleting?.name ?? "Service"}`}
        destructive
        pending={deleteService.isPending}
        onConfirm={() =>
          deleting &&
          deleteService.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(`${deleting.name} deleted`)
              setDeleting(null)
            },
            onError: (error) =>
              toast.error("Couldn't delete the Service", {
                description: error instanceof ApiError ? error.message : undefined,
              }),
          })
        }
      />
    </div>
  )
}
