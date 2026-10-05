/**
 * SCR-10 Test route (PR-13, FR-10, US-21): "what would happen to this request?" — answered by the Gateway's own
 * decision code through `POST /me/test-route`. Nothing is sent upstream.
 */
import { ArrowRightIcon, FlaskConicalIcon } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link } from "react-router"

import { ApiError } from "@/api/client"
import { useMe, usePublicBaseUrl } from "@/api/queries/me"
import { useTestRoute } from "@/api/queries/test-route"
import { HTTP_METHODS, type HttpMethodOrAny, type TestRouteResult } from "@/api/types"
import { KeyValueEditor, MethodBadge, PageHeader, PatternText, ProblemAlert, StatusCode } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { developerBaseUrl, formatDelay } from "@/lib/format"
import type { KeyValueRow } from "@/lib/validation"

import { buildRequest } from "./build-request"

/** `ANY` is a rule method, not something a request can use. */
const REQUEST_METHODS = HTTP_METHODS.filter((m) => m !== "ANY")

const ERROR_HELP: Record<string, string> = {
  service_not_resolved: "No Service owns this path. Check the path prefix in Services.",
  upstream_unreachable: "The Service's upstream host is no longer allowed. Ask an admin to check the catalog.",
  developer_not_found: "Your workspace isn't active yet: claim a slug first, or ask an admin if you are disabled.",
}

const OUTCOME: Record<TestRouteResult["outcome"], { title: string; tone: string }> = {
  mock: { title: "Mocked", tone: "bg-accent-amber" },
  proxy: { title: "Proxied", tone: "bg-accent-teal" },
  error: { title: "Error", tone: "bg-error" },
}

function ResultCard({ result }: { result: TestRouteResult }) {
  const { title, tone } = OUTCOME[result.outcome]
  return (
    <section aria-labelledby="result-title" className="space-y-4 rounded-xl border bg-canvas p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-7 items-center gap-2 rounded-full bg-surface-card px-3 type-caption text-ink">
          <span aria-hidden className={`size-2 rounded-full ${tone}`} />
          <span id="result-title">{title}</span>
        </span>
        <p className="text-ink" data-testid="outcome-reason">
          {result.reason}
        </p>
      </div>

      {result.outcome === "mock" && result.rule ? (
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-2.5 text-[14px]">
          <dt className="text-muted-foreground">Rule</dt>
          <dd>
            <Link to={`/rules/${result.rule.id}`} className="font-medium text-ink underline underline-offset-2">
              {result.rule.name}
            </Link>
          </dd>
          <dt className="text-muted-foreground">Matches</dt>
          <dd className="flex flex-wrap items-center gap-2">
            <MethodBadge method={result.rule.method} />
            <PatternText pattern={result.rule.pattern} matchType={result.rule.matchType} />
            <span className="text-muted-foreground">
              ({result.rule.matchType}, priority {result.rule.priority})
            </span>
          </dd>
          <dt className="text-muted-foreground">Active scenario</dt>
          <dd className="flex items-center gap-2">
            <span className="font-mono text-[13px]">{result.rule.activeResponse.name}</span>
            <StatusCode code={result.rule.activeResponse.statusCode} />
            <span className="text-muted-foreground">after {formatDelay(result.rule.activeResponse.delayMs)}</span>
          </dd>
        </dl>
      ) : null}

      {result.outcome === "proxy" ? (
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-2.5 text-[14px]">
          {result.service ? (
            <>
              <dt className="text-muted-foreground">Service</dt>
              <dd className="text-ink">
                {result.service.name} <span className="font-mono text-[13px]">({result.service.environment})</span>
              </dd>
            </>
          ) : null}
          {result.upstreamUrl ? (
            <>
              <dt className="text-muted-foreground">Upstream URL</dt>
              <dd className="font-mono text-[13px] break-all text-ink" data-testid="upstream-url">
                {result.upstreamUrl}
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}

      {result.outcome === "error" ? (
        <p className="text-body">
          {result.errorCode ? (
            <>
              <code className="font-mono text-[13px] text-ink">{result.errorCode}</code>
              {ERROR_HELP[result.errorCode] ? ` — ${ERROR_HELP[result.errorCode]}` : null}
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  )
}

export function TestRoutePage() {
  const test = useTestRoute()
  const me = useMe()
  const publicBaseUrl = usePublicBaseUrl()
  const [method, setMethod] = useState<HttpMethodOrAny>("GET")
  const [path, setPath] = useState("")
  const [query, setQuery] = useState<KeyValueRow[]>([])
  const [headers, setHeaders] = useState<KeyValueRow[]>([])
  const [pathError, setPathError] = useState<string>()

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const request = buildRequest(method, path, query, headers)
    if (!request.path.startsWith("/")) {
      setPathError("Start the path with “/”, e.g. /limsa/api/v1/dashboard.")
      return
    }
    setPathError(undefined)
    test.mutate(request, {
      onError: (error) => {
        if (error instanceof ApiError && error.fieldErrors.path?.[0]) setPathError(error.fieldErrors.path[0])
      },
    })
  }

  const slugBase = me.data?.slug ? developerBaseUrl(publicBaseUrl, me.data.slug) : publicBaseUrl
  // A `path` field error is shown on the field; anything else (or no field errors at all) gets the alert.
  const fieldKeys = test.error instanceof ApiError ? Object.keys(test.error.fieldErrors) : []
  const unmapped = fieldKeys.length === 0 || fieldKeys.some((key) => key !== "path")

  return (
    <div className="space-y-6">
      <PageHeader
        title="Test route"
        description="See what would happen to a request — mocked, proxied or an error — without sending it."
      />
      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-12">
        <form
          noValidate
          onSubmit={onSubmit}
          className="min-w-0 space-y-5 rounded-xl border bg-canvas p-5 sm:p-6 xl:col-span-7"
        >
          <div className="grid gap-5 sm:grid-cols-[10rem_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="test-method" className="type-caption text-ink">
                Method
              </Label>
              <Select value={method} onValueChange={(value) => setMethod(value as HttpMethodOrAny)}>
                <SelectTrigger id="test-method" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REQUEST_METHODS.map((m) => (
                    <SelectItem key={m} value={m} className="font-mono">
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-path" className="type-caption text-ink">
                Path
              </Label>
              <Input
                id="test-path"
                className="font-mono"
                placeholder="/limsa/api/v1/orders/42"
                spellCheck={false}
                autoComplete="off"
                value={path}
                onChange={(event) => setPath(event.target.value)}
                aria-invalid={Boolean(pathError) || undefined}
                aria-describedby={pathError ? "test-path-error test-path-help" : "test-path-help"}
              />
              <p id="test-path-help" className="text-[13px] text-muted-foreground">
                The path <strong className="font-medium text-ink">after</strong> your slug, i.e. what comes after{" "}
                <code className="font-mono text-ink">{slugBase}</code>.
              </p>
              {pathError ? (
                <p id="test-path-error" className="text-[13px] text-error">
                  {pathError}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-1.5">
            <p className="type-caption text-ink">Query parameters</p>
            <KeyValueEditor
              rows={query}
              onChange={setQuery}
              keyLabel="Query parameter"
              addLabel="Add query parameter"
              keyPlaceholder="status"
              valuePlaceholder="pending"
              emptyText="None. You can also type them in the path: /orders?status=pending."
            />
          </div>

          <div className="space-y-1.5">
            <p className="type-caption text-ink">Headers</p>
            <KeyValueEditor
              rows={headers}
              onChange={setHeaders}
              keyLabel="Header name"
              addLabel="Add header"
              keyPlaceholder="X-Feature"
              valuePlaceholder="beta"
              emptyText="None. Only needed when a rule has header conditions."
            />
          </div>

          <Button type="submit" disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test route"}
            <ArrowRightIcon aria-hidden />
          </Button>
        </form>

        <div className="min-w-0 space-y-4 xl:sticky xl:top-20 xl:col-span-5">
          {test.isError && unmapped ? <ProblemAlert error={test.error} /> : null}
          {test.data ? (
            <ResultCard result={test.data} />
          ) : (
            <div className="flex flex-col items-start gap-3 rounded-xl bg-surface-card p-6">
              <FlaskConicalIcon aria-hidden className="size-5 text-ink" strokeWidth={1.75} />
              <h2 className="type-title-md text-ink">The answer shows up here</h2>
              <p className="text-body">
                Enter a path and press “Test route”. Mockan runs the same decision as the Gateway: your rules first,
                then the Service that owns the path.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
