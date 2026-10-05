import { cn } from "@/lib/utils"

/** Mockan's own simple wordmark (prompt §2 rule 5: no third-party brand assets). */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1 font-heading text-[24px] leading-none font-semibold tracking-[-0.02em] text-ink",
        className,
      )}
    >
      Mockan
      <span aria-hidden className="size-1.5 rounded-full bg-primary" />
    </span>
  )
}
