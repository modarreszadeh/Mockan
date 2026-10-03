/**
 * The MockResponse ("Scenario") sub-form: status, content type, headers, body, delay (PR-06, US-12).
 * TODO(OQ-P1): Phase 1 edits only the active response. Phase 2 renders one of these per scenario tab; the
 * component reads/writes `response.*` in the surrounding form and is keyed by response id by its parent.
 */
import { Controller, useFormContext, useWatch } from "react-hook-form"

import { JsonEditor, KeyValueEditor } from "@/components/mockan"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { byteLength, isJsonContentType, MAX_BODY_BYTES, type RuleFormValues } from "@/lib/validation"
import { formatBytes } from "@/lib/format"

import { DelayField } from "./delay-field"
import { describedBy, Field, FormSection } from "./field"
import { StatusCodeField } from "./status-code-field"

export function ResponseForm() {
  const { control, register, formState } = useFormContext<RuleFormValues>()
  const errors = formState.errors.response
  const contentType = useWatch({ control, name: "response.contentType" })
  const json = isJsonContentType(contentType ?? "")

  return (
    <FormSection title="Response" description="What Mockan returns instead of proxying.">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id="response-name" label="Scenario name" error={errors?.name?.message}>
          <Input
            id="response-name"
            className="font-mono"
            aria-invalid={Boolean(errors?.name) || undefined}
            aria-describedby={describedBy("response-name", { error: Boolean(errors?.name) })}
            {...register("response.name")}
          />
        </Field>
        <Field
          id="response-contentType"
          label="Content type"
          error={errors?.contentType?.message}
          help="JSON content types get the JSON editor."
        >
          <Input
            id="response-contentType"
            className="font-mono"
            list="content-type-options"
            aria-invalid={Boolean(errors?.contentType) || undefined}
            aria-describedby={describedBy("response-contentType", { help: true, error: Boolean(errors?.contentType) })}
            {...register("response.contentType")}
          />
          <datalist id="content-type-options">
            <option value="application/json" />
            <option value="application/problem+json" />
            <option value="text/plain" />
            <option value="text/html" />
            <option value="text/csv" />
          </datalist>
        </Field>
      </div>

      <Field id="response-statusCode" label="Status code" error={errors?.statusCode?.message}>
        <Controller
          control={control}
          name="response.statusCode"
          render={({ field, fieldState }) => (
            <StatusCodeField
              id="response-statusCode"
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              invalid={Boolean(fieldState.error)}
              describedBy={describedBy("response-statusCode", { error: Boolean(fieldState.error) })}
            />
          )}
        />
      </Field>

      <div className="space-y-1.5">
        <p className="type-caption text-ink" id="response-headers-label">
          Headers
        </p>
        <Controller
          control={control}
          name="response.headers"
          render={({ field, fieldState }) => (
            <KeyValueEditor
              rows={field.value}
              onChange={field.onChange}
              keyLabel="Response header name"
              valueLabel="Response header value"
              addLabel="Add header"
              keyPlaceholder="Cache-Control"
              valuePlaceholder="no-store"
              emptyText="No extra headers. Content-Type and X-Mockan-Source are always set."
              errors={
                Array.isArray(fieldState.error) ? fieldState.error.map((e) => ({ key: e?.key?.message })) : undefined
              }
            />
          )}
        />
      </div>

      <Controller
        control={control}
        name="response.body"
        render={({ field, fieldState }) =>
          json ? (
            <div className="space-y-1.5">
              <p className="type-caption text-ink">Body</p>
              <JsonEditor
                id="response-body"
                label="Response body"
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                error={fieldState.error?.message}
              />
            </div>
          ) : (
            <Field
              id="response-body"
              label="Body"
              error={fieldState.error?.message}
              help={`${formatBytes(byteLength(field.value))} of ${formatBytes(MAX_BODY_BYTES)}`}
            >
              <Textarea
                id="response-body"
                className="min-h-48 font-mono text-[13px] whitespace-pre"
                wrap="off"
                spellCheck={false}
                aria-invalid={Boolean(fieldState.error) || undefined}
                aria-describedby={describedBy("response-body", { help: true, error: Boolean(fieldState.error) })}
                {...field}
              />
            </Field>
          )
        }
      />

      <Field
        id="response-delayMs"
        label="Delay"
        error={errors?.delayMs?.message}
        help="Simulate a slow backend to build loading states (0–30 000 ms)."
      >
        <Controller
          control={control}
          name="response.delayMs"
          render={({ field, fieldState }) => (
            <DelayField
              id="response-delayMs"
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              invalid={Boolean(fieldState.error)}
              describedBy={describedBy("response-delayMs", { help: true, error: Boolean(fieldState.error) })}
            />
          )}
        />
      </Field>
    </FormSection>
  )
}
