/**
 * `/__design` (dev only): the living style guide. Renders every token, type style and domain component
 * in its states (prompt §7 M0). Not linked from navigation and not included in production builds.
 */
import { InboxIcon } from "lucide-react"
import { useState, type ReactNode } from "react"

import { ApiError } from "@/api/client"
import {
  BaseUrlCard,
  CodeBlock,
  ConfirmDialog,
  CoralBadge,
  EmptyState,
  EnvBadge,
  JsonEditor,
  KeyValueEditor,
  MatchTypeBadge,
  MethodBadge,
  PageHeader,
  PatternText,
  ProblemAlert,
  SourceBadge,
  StatusCode,
  Wordmark,
} from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { HTTP_METHODS, MATCH_TYPES } from "@/api/types"
import type { KeyValueRow } from "@/lib/validation"

const COLOR_TOKENS = [
  ["--background", "canvas"],
  ["--foreground", "ink"],
  ["--primary", "primary (coral)"],
  ["--primary-active", "primary-active"],
  ["--primary-disabled", "primary-disabled / hairline"],
  ["--body", "body"],
  ["--body-strong", "body-strong"],
  ["--muted-foreground", "muted"],
  ["--muted-soft", "muted-soft"],
  ["--hairline-soft", "hairline-soft"],
  ["--surface-soft", "surface-soft"],
  ["--surface-card", "surface-card"],
  ["--surface-cream-strong", "surface-cream-strong"],
  ["--surface-dark", "surface-dark"],
  ["--surface-dark-elevated", "surface-dark-elevated"],
  ["--surface-dark-soft", "surface-dark-soft"],
  ["--on-dark", "on-dark"],
  ["--on-dark-soft", "on-dark-soft"],
  ["--accent-teal", "accent-teal"],
  ["--accent-amber", "accent-amber"],
  ["--success", "success"],
  ["--warning", "warning"],
  ["--error", "error"],
] as const

const TYPE_STYLES = [
  ["type-display-md", "Good morning, Ehtesham", "display-md 36 — Overview greeting"],
  ["type-display-sm", "Mock rules", "display-sm 28 — page title"],
  ["type-title-md", "Getting started", "title-md 18 — card / dialog title"],
  ["type-title-sm", "Match", "title-sm 16 — form section"],
  ["type-body", "Everything else is proxied to the real backend.", "body-sm 14 — default UI text"],
  ["type-caption", "Status code", "caption 13 — labels, badges, table headers"],
  ["type-overline", "Admin", "caption-uppercase 12 — sidebar group labels"],
  ["type-code", "GET /limsa/api/v1/dashboard", "code 14 — paths, patterns, URLs"],
] as const

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="border-b pb-2 type-title-md text-ink">{title}</h2>
      {children}
    </section>
  )
}

export function DesignPage() {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [json, setJson] = useState('{\n  "items": [],\n  "total": 0\n}')
  const [badJson, setBadJson] = useState('{\n  "items": [,\n}')
  const [rows, setRows] = useState<KeyValueRow[]>([
    { key: "X-Feature", operator: "equals", value: "beta" },
    { key: "Authorization", operator: "exists", value: "" },
  ])
  const [enabled, setEnabled] = useState(true)

  return (
    <main className="mx-auto max-w-6xl space-y-10 p-6 sm:p-8">
      <PageHeader
        title="Design system"
        description="Tokens, type and Mockan domain components in every state. Dev only."
        actions={<Wordmark />}
      />

      <Section title="Colour tokens">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {COLOR_TOKENS.map(([variable, name]) => (
            <li key={variable} className="space-y-1">
              <div className="h-14 rounded-lg border" style={{ background: `var(${variable})` }} />
              <p className="type-caption text-ink">{name}</p>
              <p className="font-mono text-[12px] text-muted-foreground">{variable}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Typography">
        <ul className="space-y-3">
          {TYPE_STYLES.map(([cls, sample, note]) => (
            <li key={cls} className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-6">
              <span className="w-72 shrink-0 font-mono text-[12px] text-muted-foreground">{note}</span>
              <span className={`${cls} text-ink`}>{sample}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Create mock</Button>
          <Button disabled>Disabled</Button>
          <Button variant="outline">Secondary</Button>
          <Button variant="secondary">Cream</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Delete rule</Button>
          <Button variant="link">Text link</Button>
          <Button size="sm" variant="outline">
            Small
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-surface-dark p-4">
          <Button variant="onDark">Copy</Button>
        </div>
      </Section>

      <Section title="Inputs">
        <div className="grid max-w-xl gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="d-name">Name</Label>
            <Input id="d-name" placeholder="Limsa dashboard" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="d-pattern">Pattern</Label>
            <Input id="d-pattern" className="font-mono" aria-invalid defaultValue="limsa/api" />
            <p className="text-[13px] text-error">Start the pattern with “/”.</p>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="d-switch" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="d-switch">Rule enabled</Label>
          </div>
          <Tabs defaultValue="exact">
            <TabsList>
              <TabsTrigger value="exact">Exact</TabsTrigger>
              <TabsTrigger value="template">Template</TabsTrigger>
              <TabsTrigger value="prefix">Prefix</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </Section>

      <Section title="Status language">
        <div className="flex flex-wrap gap-2">
          {HTTP_METHODS.map((m) => (
            <MethodBadge key={m} method={m} />
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {MATCH_TYPES.map((m) => (
            <MatchTypeBadge key={m} matchType={m} />
          ))}
          <CoralBadge>Phase 2</CoralBadge>
        </div>
        <div className="flex flex-wrap gap-2">
          <SourceBadge source="Mocked" />
          <SourceBadge source="Proxied" />
          <SourceBadge source="Error" />
          <EnvBadge environment="stage" isDefault />
          <EnvBadge environment="dev" isOverride />
        </div>
        <div className="flex flex-wrap gap-4">
          {[200, 204, 301, 404, 422, 500, 503].map((c) => (
            <StatusCode key={c} code={c} />
          ))}
        </div>
        <div className="flex flex-col gap-1">
          <PatternText pattern="/limsa/api/v1/orders/{id}/items/{*rest}" matchType="Template" />
          <PatternText pattern="^/limsa/api/v1/(items|goods)/\d+$" matchType="Regex" />
        </div>
      </Section>

      <Section title="BaseUrlCard and CodeBlock">
        <BaseUrlCard slug="ehtesham" />
        <CodeBlock
          label="Response headers preview"
          code={
            "HTTP/1.1 200 OK\nContent-Type: application/json\nX-Mockan-Source: mock\nX-Mockan-Rule-Id: 0192f5a0-0000-7000-8000-0000000a0001"
          }
        />
      </Section>

      <Section title="JsonEditor">
        <div className="grid gap-6 lg:grid-cols-2">
          <JsonEditor id="d-json" label="Valid JSON" value={json} onChange={setJson} height={160} />
          <JsonEditor id="d-json-bad" label="Invalid JSON" value={badJson} onChange={setBadJson} height={160} />
        </div>
      </Section>

      <Section title="KeyValueEditor">
        <KeyValueEditor
          rows={rows}
          onChange={setRows}
          allowExists
          keyLabel="Header name"
          addLabel="Add header condition"
          errors={[undefined, undefined]}
        />
        <KeyValueEditor rows={[]} onChange={() => undefined} keyLabel="Header name" addLabel="Add header" />
      </Section>

      <Section title="States">
        <EmptyState
          icon={InboxIcon}
          title="No rules yet"
          description="No rules yet — all traffic is proxied. Create your first mock."
          action={<Button>Create your first mock</Button>}
        />
        <ProblemAlert
          error={
            new ApiError(502, {
              title: "Mockan couldn't load your rules",
              detail: "The Admin API is unreachable.",
              code: "upstream_unreachable",
            })
          }
          onRetry={() => undefined}
        />
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-2/3" />
        </div>
        <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
          Open ConfirmDialog
        </Button>
        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Delete “Limsa dashboard”?"
          description="The rule and its response are deleted. Requests to this path will be proxied again."
          confirmLabel="Delete rule"
          destructive
          onConfirm={() => setConfirmOpen(false)}
        />
      </Section>
    </main>
  )
}
