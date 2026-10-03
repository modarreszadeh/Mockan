/**
 * SCR-08 Settings (PR-03, US-54): display name, read-only slug with the base URL, and AllowedOrigins (D-13).
 * Saving an empty origins list asks for confirmation because browser calls would fail CORS.
 */
import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon, RotateCcwIcon, XIcon } from "lucide-react"
import { useState } from "react"
import { useFieldArray, useForm, type FieldPath } from "react-hook-form"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { useMe, useUpdateMe } from "@/api/queries/me"
import type { Developer } from "@/api/types"
import { BaseUrlCard, ConfirmDialog, PageHeader, ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { DEFAULT_ALLOWED_ORIGINS } from "@/lib/config"
import { settingsFormSchema, type SettingsFormValues } from "@/lib/validation"

const toFormValues = (developer: Developer): SettingsFormValues => ({
  displayName: developer.displayName,
  allowedOrigins: developer.allowedOrigins.map((value) => ({ value })),
})

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t pt-6 md:grid-cols-[16rem_1fr] md:gap-8">
      <div className="space-y-1">
        <h2 className="type-title-sm text-ink">{title}</h2>
        {description ? <p className="text-[13px] text-muted-foreground">{description}</p> : null}
      </div>
      <div className="min-w-0 space-y-4">{children}</div>
    </section>
  )
}

function SettingsForm({ developer }: { developer: Developer }) {
  const updateMe = useUpdateMe()
  const [confirmEmpty, setConfirmEmpty] = useState(false)
  const form = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsFormSchema),
    defaultValues: toFormValues(developer),
  })
  const origins = useFieldArray({ control: form.control, name: "allowedOrigins" })
  const { errors, isDirty } = form.formState
  const [unmapped, setUnmapped] = useState<unknown>(null)

  const save = (values: SettingsFormValues) => {
    setUnmapped(null)
    updateMe.mutate(
      { displayName: values.displayName, allowedOrigins: values.allowedOrigins.map((o) => o.value.trim()) },
      {
        onSuccess: (saved) => {
          form.reset(toFormValues(saved))
          toast.success("Saved — live in about 2 seconds")
        },
        onError: (error) => {
          const fields = error instanceof ApiError ? error.fieldErrors : {}
          let mapped = false
          for (const [path, messages] of Object.entries(fields)) {
            const field = /^allowedOrigins\.\d+$/.test(path) ? `${path}.value` : path
            if (field === "displayName" || field.startsWith("allowedOrigins.")) {
              form.setError(field as FieldPath<SettingsFormValues>, { type: "server", message: messages[0] })
              mapped = true
            }
          }
          if (!mapped) setUnmapped(error)
        },
      },
    )
  }

  const submit = form.handleSubmit((values) => {
    if (values.allowedOrigins.length === 0) setConfirmEmpty(true)
    else save(values)
  })

  return (
    <form noValidate onSubmit={submit} className="space-y-6">
      {unmapped ? <ProblemAlert error={unmapped} /> : null}

      <Section title="Profile">
        <div className="max-w-sm space-y-1.5">
          <Label htmlFor="displayName" className="type-caption text-ink">
            Display name
          </Label>
          <Input
            id="displayName"
            aria-invalid={Boolean(errors.displayName) || undefined}
            aria-describedby={errors.displayName ? "displayName-error" : undefined}
            {...form.register("displayName")}
          />
          {errors.displayName ? (
            <p id="displayName-error" className="text-[13px] text-error">
              {errors.displayName.message}
            </p>
          ) : null}
        </div>
      </Section>

      <Section title="Workspace" description="Your DeveloperSlug is the first segment of every gateway request.">
        <div className="max-w-sm space-y-1.5">
          <Label htmlFor="slug" className="type-caption text-ink">
            Workspace slug
          </Label>
          <Input
            id="slug"
            value={developer.slug ?? ""}
            readOnly
            aria-describedby="slug-note"
            className="bg-surface-soft font-mono"
          />
          <p id="slug-note" className="text-[13px] text-muted-foreground">
            Slugs can't be changed.
          </p>
        </div>
        {developer.slug ? <BaseUrlCard slug={developer.slug} /> : null}
      </Section>

      <Section
        title="Allowed origins"
        description="Browser apps on these origins can read responses from your Mockan address (CORS). Use * as a wildcard."
      >
        {origins.fields.length === 0 ? (
          <p className="rounded-lg border border-error/40 px-3 py-2 text-[13px] text-error">
            No origins: browser calls to your Mockan address will fail CORS.
          </p>
        ) : null}
        <ul className="space-y-2">
          {origins.fields.map((field, index) => {
            const error = errors.allowedOrigins?.[index]?.value?.message
            return (
              <li key={field.id} className="space-y-1">
                <div className="flex max-w-lg items-center gap-2">
                  <Input
                    aria-label={`Allowed origin ${index + 1}`}
                    aria-invalid={Boolean(error) || undefined}
                    className="font-mono text-[13px]"
                    placeholder="http://localhost:*"
                    {...form.register(`allowedOrigins.${index}.value`)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove allowed origin ${index + 1}`}
                    onClick={() => origins.remove(index)}
                  >
                    <XIcon aria-hidden />
                  </Button>
                </div>
                {error ? <p className="text-[13px] text-error">{error}</p> : null}
              </li>
            )
          })}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => origins.append({ value: "" })}>
            <PlusIcon aria-hidden />
            Add origin
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => origins.replace(DEFAULT_ALLOWED_ORIGINS.map((value) => ({ value })))}
          >
            <RotateCcwIcon aria-hidden />
            Reset to defaults
          </Button>
        </div>
      </Section>

      <div className="flex justify-end gap-2 border-t pt-6">
        <Button type="button" variant="outline" disabled={!isDirty || updateMe.isPending} onClick={() => form.reset()}>
          Discard changes
        </Button>
        <Button type="submit" disabled={!isDirty || updateMe.isPending}>
          {updateMe.isPending ? "Saving…" : "Save settings"}
        </Button>
      </div>

      <ConfirmDialog
        open={confirmEmpty}
        onOpenChange={setConfirmEmpty}
        title="Save without allowed origins?"
        description="Browser calls will fail CORS: no app running in a browser can read responses from your Mockan address until you add an origin."
        confirmLabel="Save anyway"
        destructive
        onConfirm={() => {
          setConfirmEmpty(false)
          save(form.getValues())
        }}
      />
    </form>
  )
}

export function SettingsPage() {
  const me = useMe()
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Your profile, workspace address and the origins allowed to call it." />
      {me.data ? <SettingsForm developer={me.data} /> : null}
    </div>
  )
}
