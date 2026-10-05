/**
 * Details drawer for one logged request (SCR-09, PR-12): headers and body samples exactly as the server masked
 * them (NFR-07), and **Mock this** — an Exact rule that answers the way this request was answered (FR-09).
 */
import { WandSparklesIcon } from "lucide-react"
import { Link, useNavigate } from "react-router"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { useCreateRuleFromLog } from "@/api/queries/logs"
import type { RequestLogEntry, Service } from "@/api/types"
import { CodeBlock, SourceBadge, StatusCode } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { absoluteTime, formatSample, headersText } from "@/lib/format"
import { cn } from "@/lib/utils"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="type-caption text-ink">{title}</h3>
      {children}
    </section>
  )
}

function Block({ label, code, empty }: { label: string; code: string | null | undefined; empty: string }) {
  if (!code) return <p className="text-[13px] text-muted-foreground">{empty}</p>
  return <CodeBlock label={label} code={code} className={cn("max-h-72 overflow-y-auto")} />
}

export function LogDetailsSheet({
  entry,
  services,
  onClose,
}: {
  entry: RequestLogEntry | null
  services: Service[] | undefined
  onClose: () => void
}) {
  const navigate = useNavigate()
  const mockThis = useCreateRuleFromLog()
  const service = services?.find((s) => s.id === entry?.serviceId)

  const onMockThis = () => {
    if (!entry) return
    mockThis.mutate(entry.id, {
      onSuccess: (rule) => {
        toast.success(`Created “${rule.name}” — live in about 2 seconds`)
        void navigate(`/rules/${rule.id}`)
      },
      onError: (error) =>
        toast.error("Couldn't create a rule from this request", {
          description:
            error instanceof ApiError
              ? (Object.values(error.fieldErrors)[0]?.[0] ?? error.message)
              : "Check your connection and try again.",
        }),
    })
  }

  return (
    <Sheet open={entry !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-2xl">
        {entry ? (
          <>
            <SheetHeader className="p-6">
              <SheetTitle className="font-mono text-[16px] break-all">
                {entry.method} {entry.path}
                {entry.query ? `?${entry.query}` : ""}
              </SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body">
                <SourceBadge source={entry.source} />
                <StatusCode code={entry.statusCode} />
                <span>{entry.durationMs} ms</span>
                <time dateTime={entry.timestamp}>{absoluteTime(entry.timestamp)}</time>
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 space-y-6 overflow-y-auto px-6 pb-6">
              <p className="text-[13px] text-muted-foreground">
                Secrets such as Authorization headers and tokens are masked as <code className="font-mono">***</code>.
                Bodies are samples.
              </p>
              {service ? (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
                  <dt className="text-muted-foreground">Service</dt>
                  <dd className="text-ink">{service.name}</dd>
                </dl>
              ) : null}
              <Section title="Request headers">
                <Block label="Request headers" code={headersText(entry.requestHeaders)} empty="No headers captured." />
              </Section>
              <Section title="Request body">
                <Block
                  label="Request body sample"
                  code={entry.requestBodySample ? formatSample(entry.requestBodySample) : null}
                  empty="No body."
                />
              </Section>
              <Section title="Response headers">
                <Block
                  label="Response headers"
                  code={headersText(entry.responseHeaders)}
                  empty="No headers captured."
                />
              </Section>
              <Section title="Response body">
                <Block
                  label="Response body sample"
                  code={entry.responseBodySample ? formatSample(entry.responseBodySample) : null}
                  empty="No body captured."
                />
              </Section>
            </div>
            <SheetFooter className="flex-row items-center justify-between gap-2 border-t px-6 py-4">
              {entry.source === "Mocked" ? (
                // A rule already answers this request: a second one would only compete with it by precedence.
                entry.ruleId ? (
                  <>
                    <p className="text-[13px] text-muted-foreground">A mock rule answered this request.</p>
                    <Button asChild>
                      <Link to={`/rules/${entry.ruleId}`}>Open the rule</Link>
                    </Button>
                  </>
                ) : (
                  <p className="text-[13px] text-muted-foreground">The rule that answered this was deleted.</p>
                )
              ) : (
                <>
                  <p className="text-[13px] text-muted-foreground">
                    Creates an Exact rule that returns this response next time.
                  </p>
                  <Button onClick={onMockThis} disabled={mockThis.isPending}>
                    <WandSparklesIcon aria-hidden />
                    {mockThis.isPending ? "Creating…" : "Mock this"}
                  </Button>
                </>
              )}
            </SheetFooter>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
