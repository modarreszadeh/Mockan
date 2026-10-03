import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      // Design file: buttons don't change on hover; they darken on press (prompt §4.1).
      variant: {
        // TODO(OQ-F3): white on coral is 3.28:1; switch the fill to primary-active if accessibility review rejects it.
        default:
          "bg-primary text-primary-foreground active:bg-primary-active disabled:bg-primary-disabled disabled:text-muted-foreground disabled:opacity-100",
        outline:
          "border-border bg-background text-foreground active:bg-surface-card aria-expanded:bg-surface-soft",
        secondary:
          "bg-secondary text-secondary-foreground active:bg-surface-cream-strong aria-expanded:bg-surface-cream-strong",
        ghost:
          "text-foreground active:bg-surface-card aria-expanded:bg-surface-soft",
        destructive:
          "border-destructive/30 bg-background text-destructive active:bg-destructive/10 focus-visible:border-destructive/40 focus-visible:ring-destructive/20",
        onDark:
          "bg-surface-dark-elevated text-on-dark active:bg-surface-dark-soft",
        link: "text-primary-active underline-offset-4 active:underline",
      },
      size: {
        default:
          "h-10 gap-2 px-5 has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        sm: "h-8 gap-1.5 px-3 has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        lg: "h-11 gap-2 px-6",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
