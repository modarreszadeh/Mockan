import { cn } from "@/lib/utils"

/**
 * Mockan's own logo mark: a dark tile, an "M" drawn as a path (no font needed) and the coral dot of the wordmark
 * (prompt §2 rule 5: no third-party brand assets). Decorative: the `Wordmark` next to it carries the name.
 * `public/favicon.svg` is the same drawing with literal colours.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg data-slot="logo-mark" aria-hidden viewBox="0 0 32 32" className={cn("size-14 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-surface-dark" />
      <path
        d="M7.5 22V10.5L13.75 18L20 10.5V22"
        fill="none"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-on-dark"
      />
      <circle cx="25.5" cy="21" r="2" className="fill-primary" />
    </svg>
  )
}
