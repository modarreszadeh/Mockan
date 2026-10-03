/**
 * SCR-02 Onboarding (PR-01, PR-18, US-01): claim a DeveloperSlug once, then show the `.env` line and the next
 * step. Validation mirrors arch §10; a taken slug (409) lands inline on the field.
 */
import { zodResolver } from "@hookform/resolvers/zod"
import { ArrowRightIcon, CheckIcon } from "lucide-react"
import { useState } from "react"
import { useForm, useWatch } from "react-hook-form"
import { Link, Navigate } from "react-router"
import { z } from "zod"

import { ApiError } from "@/api/client"
import { useMe, useUpdateMe } from "@/api/queries/me"
import { BaseUrlCard, ConfirmDialog, ProblemAlert, Wordmark } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { developerBaseUrl } from "@/lib/format"
import { slugProblem, slugSchema } from "@/lib/validation"

const formSchema = z.object({ slug: slugSchema })
type FormValues = z.infer<typeof formSchema>

/** Suggest a slug from the display name, e.g. "Ehtesham K." → "ehtesham-k". */
function suggestSlug(displayName: string) {
  const slug = displayName
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^[^a-z]+/, "")
    .replace(/-+$/, "")
    .slice(0, 32)
  return slugProblem(slug) ? "" : slug
}

function Steps({ current }: { current: 1 | 2 }) {
  const steps = ["Claim your slug", "Point your app at Mockan"]
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-2" aria-label="Onboarding steps">
      {steps.map((label, index) => {
        const n = index + 1
        const done = n < current
        const active = n === current
        return (
          <li key={label} className="flex items-center gap-2 type-caption" aria-current={active ? "step" : undefined}>
            <span
              className={
                done || active
                  ? "flex size-6 items-center justify-center rounded-full bg-surface-dark text-[12px] text-on-dark"
                  : "flex size-6 items-center justify-center rounded-full border text-[12px] text-muted-foreground"
              }
            >
              {done ? <CheckIcon aria-hidden className="size-3.5" /> : n}
            </span>
            <span className={active ? "text-ink" : "text-muted-foreground"}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}

function ClaimStep({
  displayName,
  onClaimStart,
  onClaimFailed,
}: {
  displayName: string
  onClaimStart: () => void
  onClaimFailed: () => void
}) {
  const updateMe = useUpdateMe()
  const [confirming, setConfirming] = useState(false)
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { slug: suggestSlug(displayName) },
    mode: "onChange",
  })
  const slug = useWatch({ control: form.control, name: "slug" })
  const error = form.formState.errors.slug?.message
  const unexpectedError = updateMe.error && !(updateMe.error instanceof ApiError && updateMe.error.fieldErrors.slug)

  const claim = () => {
    // Flag first: the /me cache gets the new slug before this mutation's callbacks run.
    onClaimStart()
    updateMe.mutate(
      { slug },
      {
        onSuccess: () => setConfirming(false),
        onError: (err) => {
          setConfirming(false)
          onClaimFailed()
          const message = err instanceof ApiError ? err.fieldErrors.slug?.[0] : undefined
          if (message) form.setError("slug", { type: "server", message }, { shouldFocus: true })
        },
      },
    )
  }

  return (
    <form noValidate onSubmit={form.handleSubmit(() => setConfirming(true))} className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="slug" className="type-caption text-ink">
          Workspace slug
        </Label>
        <Input
          id="slug"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          className="max-w-sm font-mono"
          placeholder="e.g. ehtesham"
          aria-invalid={Boolean(error) || undefined}
          aria-describedby="slug-help slug-error"
          {...form.register("slug")}
        />
        <p id="slug-help" className="text-muted-foreground">
          2–32 characters: lowercase letters, digits and hyphens, starting with a letter. You can't change it later.
        </p>
        <p id="slug-error" className="min-h-5 text-[13px] text-error" aria-live="polite">
          {error}
        </p>
      </div>

      <div className="space-y-1.5 rounded-xl border bg-canvas p-4">
        <p className="type-caption text-muted-foreground">Your base URL will be</p>
        <p className="overflow-x-auto font-mono text-[14px] whitespace-nowrap text-ink" data-testid="base-url-preview">
          {developerBaseUrl("")}
          <span className={error || !slug ? "text-muted-soft" : "text-primary-active"}>{slug || "your-slug"}</span>
        </p>
      </div>

      {unexpectedError ? <ProblemAlert error={updateMe.error} /> : null}

      <Button type="submit" disabled={updateMe.isPending}>
        Continue
        <ArrowRightIcon aria-hidden />
      </Button>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Claim “${slug}”?`}
        description={
          <>
            Your slug <strong className="font-medium text-ink">cannot be changed later</strong>. Your base URL will be{" "}
            <code className="font-mono text-ink">{developerBaseUrl(slug)}</code>.
          </>
        }
        confirmLabel="Claim slug"
        pending={updateMe.isPending}
        onConfirm={claim}
      />
    </form>
  )
}

function DoneStep({ slug }: { slug: string }) {
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h2 className="type-title-md text-ink">1. Point your app at Mockan</h2>
        <BaseUrlCard slug={slug} />
      </section>
      <section className="space-y-3 rounded-xl bg-surface-card p-6">
        <h2 className="type-title-md text-ink">2. Start your app — everything is proxied until you add a mock</h2>
        <p className="text-body">
          Login, tokens and existing pages keep working against the real backend. Mock only the routes that aren't ready
          yet.
        </p>
        <div className="flex flex-wrap gap-2 pt-2">
          <Button asChild>
            <Link to="/rules/new">Create your first mock</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/">Go to overview</Link>
          </Button>
        </div>
      </section>
    </div>
  )
}

export function OnboardingPage() {
  const me = useMe()
  const [claimed, setClaimed] = useState(false)
  const developer = me.data
  if (!developer) return null
  // Already onboarded (and not just now): nothing to do here.
  if (developer.slug && !claimed) return <Navigate to="/" replace />

  return (
    <div className="min-h-svh">
      <header className="px-4 py-5 sm:px-8">
        <Wordmark />
      </header>
      <main id="main" className="mx-auto max-w-2xl space-y-8 px-4 pt-4 pb-16 sm:px-8 sm:pt-10">
        <Steps current={developer.slug ? 2 : 1} />
        <div className="space-y-2">
          <h1 className="type-display-sm text-ink">
            {developer.slug ? `You're all set, ${developer.displayName}` : "Claim your workspace"}
          </h1>
          <p className="text-body">
            {developer.slug
              ? "Your personal Mockan address is ready. Only your rules apply to it."
              : "Your slug is the first part of every request your app sends to Mockan. Only your rules apply to it, so your mocks never affect teammates."}
          </p>
        </div>
        {developer.slug ? (
          <DoneStep slug={developer.slug} />
        ) : (
          <ClaimStep
            displayName={developer.displayName}
            onClaimStart={() => setClaimed(true)}
            onClaimFailed={() => setClaimed(false)}
          />
        )}
      </main>
    </div>
  )
}
