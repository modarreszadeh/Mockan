import { CheckIcon, CopyIcon } from "lucide-react"

import { type CodeLanguage, type TokenKind, languageLabel, tokenize } from "@/lib/highlight"
import { cn } from "@/lib/utils"

import { useCopy } from "./use-copy"

export interface CodeBlockProps {
  code: string
  /** Accessible name for the scrollable region, e.g. "Response headers preview". */
  label: string
  /** Shown at the top-left and picks the syntax colours. Default `text` (no colours). */
  language?: CodeLanguage
  className?: string
}

const TOKEN_CLASS: Record<TokenKind, string> = {
  key: "text-on-dark",
  string: "text-success",
  number: "text-accent-amber",
  keyword: "text-primary",
  punctuation: "text-on-dark-soft",
  plain: "",
}

/**
 * Read-only code window: a `surface-dark-elevated` header with the language at the top-left and a copy button,
 * over a `surface-dark-soft` body with syntax colours from the dark tokens. The body scrolls both ways, never wraps.
 * `className` sizes the whole window (e.g. `max-h-72`).
 */
export function CodeBlock({ code, label, language = "text", className }: CodeBlockProps) {
  const { copied, copy } = useCopy()

  return (
    <div className={cn("flex flex-col overflow-hidden rounded-xl bg-surface-dark-soft", className)}>
      <div className="flex shrink-0 items-center justify-between gap-2 bg-surface-dark-elevated py-1.5 pr-2 pl-4">
        <span className="type-code-sm text-on-dark-soft" data-testid="code-language">
          {languageLabel[language]}
        </span>
        <button
          type="button"
          onClick={() => void copy(code)}
          aria-label={copied ? `Copied ${label}` : `Copy ${label}`}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 type-caption text-on-dark-soft outline-none hover:text-on-dark focus-visible:ring-3 focus-visible:ring-ring/30 active:bg-surface-dark-soft"
        >
          {copied ? <CheckIcon className="size-4" aria-hidden /> : <CopyIcon className="size-4" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        tabIndex={0}
        role="region"
        aria-label={label}
        className="min-h-0 flex-1 overflow-auto p-4 type-code-sm whitespace-pre text-on-dark focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none focus-visible:ring-inset"
      >
        <code>
          {tokenize(code, language).map((token, index) =>
            token.kind === "plain" ? (
              token.text
            ) : (
              <span key={index} className={TOKEN_CLASS[token.kind]}>
                {token.text}
              </span>
            ),
          )}
        </code>
      </pre>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied to clipboard" : ""}
      </span>
    </div>
  )
}
