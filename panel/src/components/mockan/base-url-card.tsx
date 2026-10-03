import { CheckIcon, CopyIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { envLine } from "@/lib/format"
import { cn } from "@/lib/utils"

import { useCopy } from "./use-copy"

export interface BaseUrlCardProps {
  slug: string
  /** Short line under the snippet. */
  hint?: string
  className?: string
}

/**
 * The `.env` line for the Developer's gateway (`code-window-card` recipe): `surface-dark`, 16 px radius,
 * mono snippet, copy button with a "Copied" confirmation. The only dark surface on most pages.
 */
export function BaseUrlCard({
  slug,
  hint = "Put this in your app's .env. Everything you don't mock is proxied to the real backend.",
  className,
}: BaseUrlCardProps) {
  const line = envLine(slug)
  const { copied, copy } = useCopy()

  return (
    <section
      aria-labelledby="base-url-title"
      className={cn("rounded-2xl bg-surface-dark p-5 text-on-dark sm:p-6", className)}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1 space-y-2">
          <h2 id="base-url-title" className="type-overline text-on-dark-soft">
            Your base URL
          </h2>
          <div
            className="overflow-x-auto rounded-lg bg-surface-dark-soft px-4 py-3"
            tabIndex={0}
            role="region"
            aria-label=".env line"
          >
            <code className="type-code whitespace-pre text-on-dark" data-testid="env-line">
              {line}
            </code>
          </div>
        </div>
        <Button
          variant="onDark"
          className="shrink-0 sm:self-end"
          onClick={() => void copy(line)}
          aria-label={copied ? "Copied .env line" : "Copy .env line"}
        >
          {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="mt-3 text-on-dark-soft">{hint}</p>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied to clipboard" : ""}
      </span>
    </section>
  )
}
