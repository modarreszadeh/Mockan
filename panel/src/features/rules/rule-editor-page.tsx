/**
 * SCR-05 Rule editor (PR-05, PR-06, US-03, US-04, US-12): `/rules/new` and `/rules/:ruleId`.
 * Server validation errors land on the matching field; unsaved changes ask before leaving.
 */
import { zodResolver } from "@hookform/resolvers/zod"
import { ChevronDownIcon, SearchXIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { Controller, FormProvider, useForm, useFormContext, useWatch, type FieldPath } from "react-hook-form"
import { Link, useBlocker, useNavigate, useParams } from "react-router"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { LIVE_SOON, useDeleteRule, useRule, useSaveRule } from "@/api/queries/rules"
import { useServices } from "@/api/queries/services"
import { HTTP_METHODS, MATCH_TYPES, type MatchType, type MockRule, type Service } from "@/api/types"
import { ConfirmDialog, EmptyState, KeyValueEditor, PageHeader, ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { ruleFormSchema, type RuleFormValues } from "@/lib/validation"

import { describedBy, Field, FormSection } from "./field"
import { ResponseForm } from "./response-form"
import { ANY_SERVICE, formFieldFor, NEW_RULE_DEFAULTS, toFormValues, toSaveInput } from "./rule-form-model"
import { RuleSummary } from "./rule-summary"

/** Help text and examples per match type (arch §7.1). */
const MATCH_HELP: Record<MatchType, { help: string; example: string }> = {
  Exact: {
    help: "Exactly this path. Case-insensitive; a trailing slash is ignored.",
    example: "/limsa/api/v1/dashboard",
  },
  Template: {
    help: "{name} matches one segment; {*name} as the last segment matches the rest of the path.",
    example: "/limsa/api/v1/orders/{id}",
  },
  Prefix: { help: "Any path that starts with this (case-insensitive).", example: "/limsa/api/v1/reports/" },
  Regex: {
    help: "RE2 syntax, at most 512 characters. Searches the path; anchor with ^…$ for a full match.",
    example: "^/limsa/api/v1/(items|goods)/\\d+$",
  },
}

/** Typed form context for the editor sections. */
const useFormContextTyped = () => useFormContext<RuleFormValues>()

function MatchSection({ services }: { services: Service[] | undefined }) {
  const { control, register, formState } = useFormContextTyped()
  const errors = formState.errors
  const matchType = useWatch({ control, name: "matchType" })
  const { help, example } = MATCH_HELP[matchType]

  return (
    <FormSection title="Match" description="Which requests this rule answers.">
      <Field id="name" label="Name" error={errors.name?.message}>
        <Input
          id="name"
          placeholder="Limsa dashboard"
          aria-invalid={Boolean(errors.name) || undefined}
          aria-describedby={describedBy("name", { error: Boolean(errors.name) })}
          {...register("name")}
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-[10rem_1fr]">
        <Field id="method" label="Method" error={errors.method?.message}>
          <Controller
            control={control}
            name="method"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="method" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HTTP_METHODS.map((m) => (
                    <SelectItem key={m} value={m} className="font-mono">
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </Field>

        <div className="space-y-1.5">
          <p id="matchType-label" className="type-caption text-ink">
            Match type
          </p>
          <Controller
            control={control}
            name="matchType"
            render={({ field }) => (
              <ToggleGroup
                type="single"
                spacing={0}
                variant="outline"
                value={field.value}
                onValueChange={(next) => next && field.onChange(next)}
                aria-labelledby="matchType-label"
                className="w-full flex-wrap sm:w-fit"
              >
                {MATCH_TYPES.map((t) => (
                  <ToggleGroupItem
                    key={t}
                    value={t}
                    className="flex-1 text-body data-[state=on]:bg-surface-card data-[state=on]:text-ink sm:flex-none"
                  >
                    {t}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
          <p className="text-[13px] text-muted-foreground">
            {help} Example: <code className="font-mono text-ink">{example}</code>
          </p>
        </div>
      </div>

      <Field
        id="pattern"
        label="Pattern"
        error={errors.pattern?.message}
        help={
          <>
            Matches the path <strong className="font-medium text-ink">after</strong> your slug, e.g.{" "}
            <code className="font-mono text-ink">/limsa/api/v1/dashboard</code>.
          </>
        }
      >
        <Input
          id="pattern"
          className="font-mono"
          placeholder={example}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={Boolean(errors.pattern) || undefined}
          aria-describedby={describedBy("pattern", { help: true, error: Boolean(errors.pattern) })}
          {...register("pattern")}
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          id="serviceId"
          label="Service scope"
          help="Optional: only match paths routed to this Service."
          error={errors.serviceId?.message}
        >
          <Controller
            control={control}
            name="serviceId"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="serviceId" className="w-full" aria-describedby="serviceId-help">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY_SERVICE}>Any service</SelectItem>
                  {services?.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name} <span className="font-mono text-muted-foreground">{s.pathPrefix}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </Field>
        <Field id="priority" label="Priority" help="Lower wins. Default 100." error={errors.priority?.message}>
          <Input
            id="priority"
            type="number"
            inputMode="numeric"
            min={0}
            className="w-32 font-mono"
            aria-invalid={Boolean(errors.priority) || undefined}
            aria-describedby={describedBy("priority", { help: true, error: Boolean(errors.priority) })}
            {...register("priority", { valueAsNumber: true })}
          />
        </Field>
      </div>
    </FormSection>
  )
}

function ConditionsSection() {
  const { control, formState } = useFormContextTyped()
  const query = useWatch({ control, name: "queryConditions" })
  const headers = useWatch({ control, name: "headerConditions" })
  const count = query.length + headers.length
  const [open, setOpen] = useState(count > 0)
  const rowErrors = (name: "queryConditions" | "headerConditions") => {
    const e = formState.errors[name]
    return Array.isArray(e) ? e.map((row) => ({ key: row?.key?.message, value: row?.value?.message })) : undefined
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border bg-canvas">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 rounded-xl p-5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/30 sm:px-6"
        >
          <span className="space-y-1">
            <span className="block type-title-md text-ink">
              Conditions{count ? <span className="text-body"> ({count})</span> : null}
            </span>
            <span className="block text-muted-foreground">
              Optional: also require query parameters or headers. All must hold.
            </span>
          </span>
          <ChevronDownIcon
            aria-hidden
            className={open ? "size-5 rotate-180 transition-transform" : "size-5 transition-transform"}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-6 px-5 pb-6 sm:px-6">
        <div className="space-y-2">
          <p className="type-caption text-ink">Query conditions</p>
          <Controller
            control={control}
            name="queryConditions"
            render={({ field }) => (
              <KeyValueEditor
                rows={field.value}
                onChange={field.onChange}
                allowExists
                keyLabel="Query parameter"
                addLabel="Add query condition"
                keyPlaceholder="status"
                valuePlaceholder="pending"
                errors={rowErrors("queryConditions")}
              />
            )}
          />
        </div>
        <div className="space-y-2">
          <p className="type-caption text-ink">Header conditions</p>
          <Controller
            control={control}
            name="headerConditions"
            render={({ field }) => (
              <KeyValueEditor
                rows={field.value}
                onChange={field.onChange}
                allowExists
                keyLabel="Header name"
                addLabel="Add header condition"
                keyPlaceholder="X-Feature"
                valuePlaceholder="beta"
                errors={rowErrors("headerConditions")}
              />
            )}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function RuleForm({ rule, services }: { rule?: MockRule; services: Service[] | undefined }) {
  const navigate = useNavigate()
  const save = useSaveRule()
  const deleteRule = useDeleteRule()
  const [unmappedError, setUnmappedError] = useState<unknown>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // Set when leaving on purpose (after create/delete); the effect below navigates once the blocker sees it.
  const [leavingTo, setLeavingTo] = useState<string | null>(null)

  const form = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    defaultValues: rule ? toFormValues(rule) : NEW_RULE_DEFAULTS,
  })
  const isDirty = form.formState.isDirty

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      leavingTo === null && isDirty && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!isDirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [isDirty])

  useEffect(() => {
    if (leavingTo) void navigate(leavingTo)
  }, [leavingTo, navigate])

  const onSubmit = form.handleSubmit((values) => {
    setUnmappedError(null)
    save.mutate(toSaveInput(values, rule?.id), {
      onSuccess: (saved) => {
        toast.success(LIVE_SOON)
        form.reset(toFormValues(saved))
        if (!rule) setLeavingTo("/rules")
      },
      onError: (error) => {
        const fields = error instanceof ApiError ? error.fieldErrors : {}
        let mapped = 0
        for (const [path, messages] of Object.entries(fields)) {
          const field = formFieldFor(path)
          if (!field) continue
          form.setError(
            field as FieldPath<RuleFormValues>,
            { type: "server", message: messages[0] },
            { shouldFocus: mapped === 0 },
          )
          mapped += 1
        }
        if (mapped === 0) setUnmappedError(error)
      },
    })
  })

  return (
    <FormProvider {...form}>
      <form noValidate onSubmit={onSubmit} className="pb-24">
        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-12">
          <div className="min-w-0 space-y-6 xl:col-span-7">
            {unmappedError ? <ProblemAlert error={unmappedError} /> : null}
            <MatchSection services={services} />
            <ConditionsSection />
            {/* TODO(OQ-P1): Phase 2 turns this into scenario tabs, one ResponseForm per MockResponse. */}
            <ResponseForm key={rule?.activeResponseId ?? "new"} />
            {rule ? (
              <section className="space-y-3 rounded-xl border border-error/40 bg-canvas p-5 sm:p-6">
                <h2 className="type-title-md text-ink">Danger zone</h2>
                <p className="text-body">
                  Deleting removes the rule and its responses. Requests it matched are proxied to the real backend
                  again.
                </p>
                <Button type="button" variant="destructive" onClick={() => setConfirmDelete(true)}>
                  Delete rule
                </Button>
              </section>
            ) : null}
          </div>
          <div className="min-w-0 xl:sticky xl:top-20 xl:col-span-5">
            <RuleSummary control={form.control} services={services} ruleId={rule?.id} />
          </div>
        </div>

        <div className="sticky bottom-0 z-10 -mx-4 mt-6 flex items-center justify-end gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
          <span className="mr-auto hidden text-[13px] text-muted-foreground sm:block" aria-live="polite">
            {isDirty ? "Unsaved changes" : rule ? "All changes saved" : ""}
          </span>
          <Button type="button" variant="outline" onClick={() => void navigate("/rules")}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : rule ? "Save" : "Create rule"}
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => !open && blocker.reset?.()}
        title="Discard unsaved changes?"
        description="You have changes to this rule that aren't saved. If you leave now, they're lost."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        destructive
        onConfirm={() => blocker.proceed?.()}
      />

      {rule ? (
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={`Delete “${rule.name}”?`}
          description="The rule and its responses are deleted. Requests to this path will be proxied to the real backend again."
          confirmLabel="Delete rule"
          destructive
          pending={deleteRule.isPending}
          onConfirm={() =>
            deleteRule.mutate(rule.id, {
              onSuccess: () => {
                setConfirmDelete(false)
                toast.success("Rule deleted — requests are proxied again in about 2 seconds")
                setLeavingTo("/rules")
              },
            })
          }
        />
      ) : null}
    </FormProvider>
  )
}

function EditorSkeleton() {
  return (
    <div className="grid gap-6 xl:grid-cols-12" role="status" aria-busy="true" aria-label="Loading rule">
      <div className="space-y-6 xl:col-span-7">
        <Skeleton className="h-96 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
      <Skeleton className="h-72 xl:col-span-5" />
    </div>
  )
}

export function RuleEditorPage() {
  const { ruleId } = useParams()
  const isNew = !ruleId
  const rule = useRule(ruleId)
  const services = useServices()

  let body
  if (!isNew && rule.isError) {
    body =
      rule.error instanceof ApiError && rule.error.status === 404 ? (
        <EmptyState
          icon={SearchXIcon}
          title="This rule doesn't exist"
          description="It may have been deleted. Go back to your rules to pick another one."
          action={
            <Button asChild>
              <Link to="/rules">Back to rules</Link>
            </Button>
          }
        />
      ) : (
        <ProblemAlert error={rule.error} onRetry={() => void rule.refetch()} />
      )
  } else if (!isNew && !rule.data) {
    body = <EditorSkeleton />
  } else {
    body = <RuleForm key={ruleId ?? "new"} rule={rule.data} services={services.data} />
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={isNew ? "New rule" : (rule.data?.name ?? "Edit rule")}
        description={
          isNew
            ? "Mock one route; everything else keeps going to the real backend."
            : "Changes are live in about 2 seconds after you save."
        }
      />
      {body}
    </div>
  )
}
