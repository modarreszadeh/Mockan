/**
 * SCR-11 Shared rule (S-2, S-3): the public, read-only page behind a share link. No sign-in, no app shell, no
 * `GET /me`: it shows one MockRule live (request details and every scenario) so a teammate can review the contract.
 */
import { CheckIcon, CopyIcon, SearchXIcon } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"
import { useParams } from "react-router"

import { ApiError } from "@/api/client"
import { useSharedRule } from "@/api/queries/shared"
import type { Condition, MockResponse, SharedRule } from "@/api/types"
import {
  CodeBlock,
  MatchTypeBadge,
  MethodBadge,
  PatternText,
  ProblemAlert,
  StatusCode,
  useCopy,
  Wordmark,
} from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { absoluteTime, developerBaseUrl, formatDelay, headersText } from "@/lib/format"
import { reasonPhrase } from "@/lib/http"

import { ActiveBadge } from "../rules/scenario-bar"

/** Title and `noindex` for as long as the page is shown; the server also sends `X-Robots-Tag` (S-3). */
function usePageMeta(title: string) {
  useEffect(() => {
    const previousTitle = document.title
    document.title = title
    const meta = document.createElement("meta")
    meta.name = "robots"
    meta.content = "noindex"
    document.head.appendChild(meta)
    return () => {
      document.title = previousTitle
      meta.remove()
    }
  }, [title])
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center justify-between gap-3 px-4 py-5 sm:px-8">
        <Wordmark />
        <span className="rounded-full border border-hairline bg-canvas px-2.5 py-1 type-caption text-body">
          Read-only preview
        </span>
      </header>
      <main className="mx-auto w-full max-w-4xl space-y-6 px-4 pt-2 pb-12 sm:px-8">{children}</main>
    </div>
  )
}

function Unavailable() {
  return (
    <Shell>
      <section className="flex min-h-[50svh] flex-col justify-center gap-4">
        <SearchXIcon aria-hidden className="size-6 text-ink" strokeWidth={1.75} />
        <h1 className="type-display-sm text-ink">This link isn't available</h1>
        <div className="space-y-2 text-body">
          <p>The owner may have stopped sharing this rule, or the address is mistyped.</p>
          <p>Ask whoever sent you the link for a new one.</p>
        </div>
      </section>
    </Shell>
  )
}

function Loading() {
  return (
    <Shell>
      <div role="status" aria-busy="true" aria-label="Loading the shared rule" className="space-y-4">
        <Skeleton className="h-10 w-72 max-w-full" />
        <Skeleton className="h-56 w-full rounded-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    </Shell>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="type-caption text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-body">{children}</dd>
    </div>
  )
}

function Conditions({ label, conditions }: { label: string; conditions: Condition[] }) {
  return (
    <div className="space-y-2">
      <h3 className="type-caption text-muted-foreground">{label}</h3>
      {conditions.length === 0 ? (
        <p className="text-body">None</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <Table aria-label={label}>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Condition</TableHead>
                <TableHead>Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {conditions.map((c, index) => (
                <TableRow key={`${c.key}-${index}`}>
                  <TableCell className="font-mono text-[13px] break-all whitespace-normal">{c.key}</TableCell>
                  <TableCell>{c.operator === "exists" ? "is present" : "equals"}</TableCell>
                  <TableCell className="font-mono text-[13px] break-all whitespace-normal">
                    {c.operator === "exists" ? "—" : c.value || "(empty)"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function MockUrl({ rule }: { rule: SharedRule }) {
  const { copied, copy } = useCopy()
  const slug = rule.owner.slug
  if (!slug) return <>—</>
  const base = developerBaseUrl(rule.publicBaseUrl, slug)
  if (rule.matchType !== "Exact") {
    return (
      <span>
        <code className="font-mono text-[13px] break-all text-ink">{base}</code>
        <span className="text-muted-foreground"> followed by a path that matches the pattern</span>
      </span>
    )
  }
  const url = `${base}${rule.pattern}`
  return (
    <span className="flex flex-wrap items-center gap-2">
      <code className="min-w-0 font-mono text-[13px] break-all text-ink">{url}</code>
      <Button type="button" variant="outline" size="sm" onClick={() => void copy(url)}>
        {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
        {copied ? "Copied" : "Copy URL"}
      </Button>
    </span>
  )
}

function RequestCard({ rule }: { rule: SharedRule }) {
  return (
    <Card aria-labelledby="request-title" role="region">
      <CardHeader>
        <CardTitle>
          <h2 id="request-title" className="text-ink">
            Request
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <MethodBadge method={rule.method} />
          <MatchTypeBadge matchType={rule.matchType} />
          <PatternText pattern={rule.pattern} matchType={rule.matchType} className="min-w-0 break-all" />
        </div>
        <dl className="grid gap-4 sm:grid-cols-3">
          <Field label="Service">
            {rule.service ? (
              <>
                <span className="font-medium text-ink">{rule.service.name}</span>{" "}
                <code className="font-mono text-[13px]">{rule.service.pathPrefix}</code>
              </>
            ) : (
              "Any"
            )}
          </Field>
          <Field label="Priority">{rule.priority}</Field>
          <Field label="State">{rule.isEnabled ? "Enabled" : "Disabled — requests are proxied"}</Field>
        </dl>
        <dl>
          <Field label="Mock URL">
            <MockUrl rule={rule} />
          </Field>
        </dl>
        <Conditions label="Query conditions" conditions={rule.queryConditions} />
        <Conditions label="Header conditions" conditions={rule.headerConditions} />
      </CardContent>
    </Card>
  )
}

const codeLanguage = (contentType: string) => (/json/i.test(contentType) ? "json" : "text")

/** A body pretty-printed when it is JSON; anything else is shown exactly as stored. */
function prettyBody(response: MockResponse) {
  if (!/json/i.test(response.contentType)) return response.body
  try {
    return JSON.stringify(JSON.parse(response.body), null, 2)
  } catch {
    return response.body
  }
}

function ScenarioPanel({ response }: { response: MockResponse }) {
  const phrase = reasonPhrase(response.statusCode)
  return (
    <TabsContent value={response.id} className="space-y-4 pt-4 text-base">
      <dl className="grid gap-4 sm:grid-cols-4">
        <Field label="Status">
          <StatusCode code={response.statusCode} /> {phrase}
        </Field>
        <Field label="Delay">{formatDelay(response.delayMs)}</Field>
        <Field label="Content type">
          <code className="font-mono text-[13px]">{response.contentType}</code>
        </Field>
        <Field label="Body mode">{response.bodyMode}</Field>
      </dl>
      <div className="space-y-1.5">
        <h3 className="type-caption text-ink">Response headers</h3>
        {Object.keys(response.headers).length === 0 ? (
          <p className="text-body">None besides the content type</p>
        ) : (
          <CodeBlock
            label={`Response headers of ${response.name}`}
            code={headersText(response.headers)}
            language="http"
          />
        )}
      </div>
      <div className="space-y-1.5">
        <h3 className="type-caption text-ink">Body</h3>
        {response.body === "" ? (
          <p className="text-body">Empty</p>
        ) : (
          <CodeBlock
            label={`Body of ${response.name}`}
            code={prettyBody(response)}
            language={codeLanguage(response.contentType)}
            className="max-h-96"
          />
        )}
      </div>
    </TabsContent>
  )
}

function ScenariosCard({ rule }: { rule: SharedRule }) {
  const firstId = rule.activeResponseId ?? rule.responses[0]?.id ?? ""
  const [selected, setSelected] = useState(firstId)
  const current = rule.responses.some((r) => r.id === selected) ? selected : firstId
  return (
    <Card role="region" aria-labelledby="scenarios-title">
      <CardHeader>
        <CardTitle>
          <h2 id="scenarios-title" className="text-ink">
            Scenarios
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs value={current} onValueChange={setSelected} className="gap-0">
          <div className="overflow-x-auto">
            <TabsList aria-label="Scenarios" className="h-auto w-max max-w-none flex-nowrap gap-1 p-1">
              {rule.responses.map((response) => (
                <TabsTrigger key={response.id} value={response.id} className="h-9 flex-none gap-2 px-3">
                  <span className="max-w-40 truncate font-mono text-[13px]">{response.name}</span>
                  <StatusCode code={response.statusCode} />
                  {response.id === rule.activeResponseId ? <ActiveBadge /> : null}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {rule.responses.map((response) => (
            <ScenarioPanel key={response.id} response={response} />
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}

function SharedRuleView({ rule }: { rule: SharedRule }) {
  return (
    <Shell>
      <header className="space-y-1">
        <h1 className="type-display-sm break-words text-ink">{rule.name}</h1>
        <p className="text-body">
          Shared by <span className="font-medium text-ink">{rule.owner.displayName}</span> · Updated{" "}
          <time dateTime={rule.updatedAt}>{absoluteTime(rule.updatedAt)}</time>
        </p>
        <p className="text-[13px] text-muted-foreground">
          This is the rule as it is right now. Refresh the page to see changes.
        </p>
      </header>
      <RequestCard rule={rule} />
      <ScenariosCard rule={rule} />
    </Shell>
  )
}

export function SharedRulePage() {
  const { token } = useParams()
  const query = useSharedRule(token)
  usePageMeta(query.isSuccess ? `${query.data.name} · Mockan` : "Shared rule · Mockan")

  if (query.isPending) return <Loading />
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <Unavailable />
    return (
      <Shell>
        <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />
      </Shell>
    )
  }
  return <SharedRuleView rule={query.data} />
}
