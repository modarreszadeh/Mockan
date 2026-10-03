/**
 * Create/edit a Service and its environments in a right Sheet (SCR-07, PR-10). The server rejects base URLs
 * whose host isn't allowlisted (PR-15, NFR-06); that error lands inline on the base URL field.
 */
import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon, Trash2Icon } from "lucide-react"
import { useState } from "react"
import { Controller, useFieldArray, useForm, useWatch, type FieldPath } from "react-hook-form"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { CatalogSaveError, useSaveService, useServices } from "@/api/queries/services"
import { ENVIRONMENTS, type Service } from "@/api/types"
import { KeyValueEditor, ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import { recordToRows, rowsToRecord } from "@/lib/format"
import { serviceFormSchema, type EnvironmentFormValues, type ServiceFormValues } from "@/lib/validation"

export const ALLOWLIST_MESSAGE = "Only allowlisted dev/stage hosts can be used."

const SERVICE_FIELDS = new Set(["name", "pathPrefix", "stripPrefix", "rewriteOrigin", "defaultEnvironment"])
const ENVIRONMENT_FIELDS = new Set(["environment", "baseUrl", "timeoutSeconds", "extraHeaders"])

const newEnvironment = (environment: "dev" | "stage"): EnvironmentFormValues => ({
  environment,
  baseUrl: "",
  timeoutSeconds: 100,
  extraHeaders: [],
})

function toFormValues(service: Service | null): ServiceFormValues {
  if (!service)
    return {
      name: "",
      pathPrefix: "/",
      stripPrefix: false,
      rewriteOrigin: false,
      defaultEnvironment: "stage",
      environments: [newEnvironment("stage")],
    }
  return {
    name: service.name,
    pathPrefix: service.pathPrefix,
    stripPrefix: service.stripPrefix,
    rewriteOrigin: service.rewriteOrigin,
    defaultEnvironment: service.defaultEnvironment,
    environments: service.environments.map((e) => ({
      id: e.id,
      environment: e.environment,
      baseUrl: e.baseUrl,
      timeoutSeconds: e.timeoutSeconds,
      extraHeaders: recordToRows(e.extraHeaders),
    })),
  }
}

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="text-[13px] text-error">
      {message}
    </p>
  ) : null
}

function SwitchRow({
  id,
  label,
  help,
  checked,
  onChange,
}: {
  id: string
  label: string
  help: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <Label htmlFor={id} className="type-caption text-ink">
          {label}
        </Label>
        <p id={`${id}-help`} className="text-[13px] text-muted-foreground">
          {help}
        </p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} aria-describedby={`${id}-help`} />
    </div>
  )
}

function ServiceForm({ service, onDone }: { service: Service | null; onDone: () => void }) {
  const save = useSaveService()
  const catalog = useServices()
  // A create that failed on an environment still created the Service; later saves update it.
  const [serviceId, setServiceId] = useState<string | undefined>(service?.id)
  const current = catalog.data?.find((s) => s.id === serviceId) ?? (serviceId === service?.id ? service : null)
  const [unmapped, setUnmapped] = useState<unknown>(null)
  const form = useForm<ServiceFormValues>({
    resolver: zodResolver(serviceFormSchema),
    defaultValues: toFormValues(service),
  })
  const environments = useFieldArray({ control: form.control, name: "environments" })
  const errors = form.formState.errors
  const envValues = useWatch({ control: form.control, name: "environments" })
  const missing = ENVIRONMENTS.filter((env) => !envValues.some((e) => e.environment === env))

  const onSubmit = form.handleSubmit((values) => {
    setUnmapped(null)
    save.mutate(
      {
        serviceId,
        previous: current?.environments ?? [],
        service: {
          name: values.name.trim(),
          pathPrefix: values.pathPrefix.trim(),
          stripPrefix: values.stripPrefix,
          rewriteOrigin: values.rewriteOrigin,
          defaultEnvironment: values.defaultEnvironment,
        },
        environments: values.environments.map((e) => ({
          // Rows saved by an earlier, partly failed attempt have no id in the form yet.
          id: e.id ?? current?.environments.find((x) => x.environment === e.environment)?.id,
          environment: e.environment,
          baseUrl: e.baseUrl.trim(),
          timeoutSeconds: e.timeoutSeconds,
          extraHeaders: rowsToRecord(e.extraHeaders),
        })),
      },
      {
        onSuccess: (saved) => {
          toast.success(`${saved.name} saved — live in about 2 seconds`)
          onDone()
        },
        onError: (error) => {
          if (!(error instanceof CatalogSaveError)) return setUnmapped(error)
          // Keep going as an edit of the Service that now exists.
          if (error.serviceId) setServiceId(error.serviceId)
          const cause = error.cause
          const fields = cause instanceof ApiError ? cause.fieldErrors : {}
          let mapped = 0
          for (const [path, messages] of Object.entries(fields)) {
            let message = messages[0]
            let field: string | undefined
            if (error.environmentIndex === undefined && SERVICE_FIELDS.has(path)) field = path
            if (error.environmentIndex !== undefined && ENVIRONMENT_FIELDS.has(path)) {
              field = `environments.${error.environmentIndex}.${path}`
              if (path === "baseUrl" && cause instanceof ApiError && cause.code === "upstream_host_not_allowed")
                message = ALLOWLIST_MESSAGE
            }
            if (!field) continue
            form.setError(
              field as FieldPath<ServiceFormValues>,
              { type: "server", message },
              { shouldFocus: mapped === 0 },
            )
            mapped += 1
          }
          if (mapped === 0) setUnmapped(cause)
        },
      },
    )
  })

  return (
    <form noValidate onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 pb-6">
        {unmapped ? <ProblemAlert error={unmapped} /> : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="svc-name" className="type-caption text-ink">
              Name
            </Label>
            <Input
              id="svc-name"
              className="font-mono"
              placeholder="limsa"
              aria-invalid={Boolean(errors.name) || undefined}
              aria-describedby={errors.name ? "svc-name-error" : undefined}
              {...form.register("name")}
            />
            <FieldError id="svc-name-error" message={errors.name?.message} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="svc-pathPrefix" className="type-caption text-ink">
              Path prefix
            </Label>
            <Input
              id="svc-pathPrefix"
              className="font-mono"
              placeholder="/limsa"
              aria-invalid={Boolean(errors.pathPrefix) || undefined}
              aria-describedby={errors.pathPrefix ? "svc-pathPrefix-error" : undefined}
              {...form.register("pathPrefix")}
            />
            <FieldError id="svc-pathPrefix-error" message={errors.pathPrefix?.message} />
          </div>
        </div>

        <div className="space-y-4 rounded-xl border p-4">
          <Controller
            control={form.control}
            name="stripPrefix"
            render={({ field }) => (
              <SwitchRow
                id="svc-stripPrefix"
                label="Strip prefix"
                help="Remove the path prefix before forwarding upstream."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={form.control}
            name="rewriteOrigin"
            render={({ field }) => (
              <SwitchRow
                id="svc-rewriteOrigin"
                label="Rewrite origin"
                help="Send the upstream origin in Origin/Referer, for backends that reject foreign origins."
                checked={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="svc-defaultEnvironment" className="type-caption text-ink">
            Default environment
          </Label>
          <Controller
            control={form.control}
            name="defaultEnvironment"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger
                  id="svc-defaultEnvironment"
                  className="w-40 font-mono"
                  aria-describedby="svc-defaultEnvironment-help"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ENVIRONMENTS.map((env) => (
                    <SelectItem key={env} value={env} className="font-mono">
                      {env}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <p id="svc-defaultEnvironment-help" className="text-[13px] text-muted-foreground">
            Used by Developers who haven't picked an environment.
          </p>
          <FieldError id="svc-defaultEnvironment-error" message={errors.defaultEnvironment?.message} />
        </div>

        <section className="space-y-3" aria-labelledby="envs-title">
          <div className="flex items-center justify-between gap-2">
            <h3 id="envs-title" className="type-title-sm text-ink">
              Environments
            </h3>
            {missing.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => environments.append(newEnvironment(missing[0]!))}
              >
                <PlusIcon aria-hidden />
                Add {missing[0]}
              </Button>
            ) : null}
          </div>
          {errors.environments?.root?.message || errors.environments?.message ? (
            <p className="text-[13px] text-error">{errors.environments.root?.message ?? errors.environments.message}</p>
          ) : null}
          {environments.fields.map((field, index) => {
            const envErrors = errors.environments?.[index]
            const prefix = `env-${index}`
            return (
              <div key={field.id} className="space-y-4 rounded-xl border p-4">
                <div className="flex items-end gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor={`${prefix}-environment`} className="type-caption text-ink">
                      Environment
                    </Label>
                    <Controller
                      control={form.control}
                      name={`environments.${index}.environment`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger id={`${prefix}-environment`} className="w-32 font-mono">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ENVIRONMENTS.map((env) => (
                              <SelectItem key={env} value={env} className="font-mono">
                                {env}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`${prefix}-timeout`} className="type-caption text-ink">
                      Timeout (s)
                    </Label>
                    <Input
                      id={`${prefix}-timeout`}
                      type="number"
                      min={1}
                      className="w-24 font-mono"
                      aria-invalid={Boolean(envErrors?.timeoutSeconds) || undefined}
                      {...form.register(`environments.${index}.timeoutSeconds`, { valueAsNumber: true })}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="ml-auto"
                    aria-label={`Remove ${envValues[index]?.environment ?? "environment"} environment`}
                    onClick={() => environments.remove(index)}
                  >
                    <Trash2Icon aria-hidden />
                  </Button>
                </div>
                <FieldError id={`${prefix}-environment-error`} message={envErrors?.environment?.message} />
                <FieldError id={`${prefix}-timeout-error`} message={envErrors?.timeoutSeconds?.message} />
                <div className="space-y-1.5">
                  <Label htmlFor={`${prefix}-baseUrl`} className="type-caption text-ink">
                    Base URL
                  </Label>
                  <Input
                    id={`${prefix}-baseUrl`}
                    className="font-mono text-[13px]"
                    placeholder="https://limsa.dev.internal"
                    aria-invalid={Boolean(envErrors?.baseUrl) || undefined}
                    aria-describedby={envErrors?.baseUrl ? `${prefix}-baseUrl-error` : undefined}
                    {...form.register(`environments.${index}.baseUrl`)}
                  />
                  <FieldError id={`${prefix}-baseUrl-error`} message={envErrors?.baseUrl?.message} />
                </div>
                <div className="space-y-1.5">
                  <p className="type-caption text-ink">Extra headers</p>
                  <Controller
                    control={form.control}
                    name={`environments.${index}.extraHeaders`}
                    render={({ field: f }) => (
                      <KeyValueEditor
                        rows={f.value}
                        onChange={f.onChange}
                        keyLabel={`Extra header name (${envValues[index]?.environment ?? ""})`}
                        valueLabel={`Extra header value (${envValues[index]?.environment ?? ""})`}
                        addLabel="Add header"
                        emptyText="None — added to every upstream request in this environment."
                      />
                    )}
                  />
                </div>
              </div>
            )
          })}
        </section>
      </div>
      <SheetFooter className="flex-row justify-end gap-2 border-t px-6 py-4">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : service ? "Save Service" : "Create Service"}
        </Button>
      </SheetFooter>
    </form>
  )
}

export function ServiceSheet({
  open,
  service,
  onOpenChange,
}: {
  open: boolean
  /** `null` creates a new Service. */
  service: Service | null
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-xl">
        <SheetHeader className="p-6">
          <SheetTitle>{service ? `Edit ${service.name}` : "Add a Service"}</SheetTitle>
          <SheetDescription className="text-body">
            Path prefix and base URLs decide where Developers' requests are proxied. {ALLOWLIST_MESSAGE}
          </SheetDescription>
        </SheetHeader>
        {open ? <ServiceForm key={service?.id ?? "new"} service={service} onDone={() => onOpenChange(false)} /> : null}
      </SheetContent>
    </Sheet>
  )
}
