/**
 * The Panel's one overlay panel: a centered modal at ≥ 768 px, a bottom sheet below (Frontend/plan-responsive-overlays.md).
 * The layout is plain CSS (`md:` = 768 px, the same as `useIsMobile`), so one Radix Dialog serves both and resizing
 * never remounts it. Features use `Modal` or `ConfirmDialog`, never `ui/sheet`, `ui/dialog` or `ui/alert-dialog`.
 */
import { XIcon } from "lucide-react"
import { Dialog as DialogPrimitive } from "radix-ui"
import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type ModalSize = "sm" | "md" | "lg"

const SIZE_CLASS: Record<ModalSize, string> = {
  sm: "md:max-w-sm",
  md: "md:max-w-xl",
  lg: "md:max-w-2xl",
}

export const modalOverlayClass =
  "fixed inset-0 z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0 motion-reduce:animate-none"

/** Position, size, shape and motion of the surface; shared by `Modal` and `ConfirmDialog`. */
export function modalSurfaceClass(size: ModalSize = "md") {
  return cn(
    // Bottom sheet.
    "fixed inset-x-0 bottom-0 z-50 flex max-h-[90dvh] w-full flex-col rounded-t-xl bg-popover pb-[env(safe-area-inset-bottom)] text-sm text-popover-foreground ring-1 ring-border duration-200 outline-none motion-reduce:animate-none data-open:animate-in data-open:fade-in-0 data-open:slide-in-from-bottom data-closed:animate-out data-closed:fade-out-0 data-closed:slide-out-to-bottom",
    // Centered modal.
    "md:inset-x-auto md:top-1/2 md:bottom-auto md:left-1/2 md:max-h-[85dvh] md:w-[calc(100%-2rem)] md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-xl md:pb-0 md:duration-100 md:data-open:slide-in-from-bottom-0 md:data-open:zoom-in-95 md:data-closed:slide-out-to-bottom-0 md:data-closed:zoom-out-95",
    SIZE_CLASS[size],
  )
}

/** Grab handle of the bottom sheet: decorative (dragging is not supported, OQ-F9). */
export function ModalHandle() {
  return <div aria-hidden className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-border md:hidden" />
}

export function Modal(props: ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="modal" {...props} />
}

export function ModalTrigger(props: ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="modal-trigger" {...props} />
}

export function ModalClose(props: ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="modal-close" {...props} />
}

export function ModalContent({
  className,
  children,
  size = "md",
  showCloseButton = true,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { size?: ModalSize; showCloseButton?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay data-slot="modal-overlay" className={modalOverlayClass} />
      <DialogPrimitive.Content data-slot="modal-content" className={cn(modalSurfaceClass(size), className)} {...props}>
        <ModalHandle />
        {children}
        {showCloseButton ? (
          <DialogPrimitive.Close asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="absolute top-2 right-2 size-11 md:top-3 md:right-3 md:size-8"
            >
              <XIcon aria-hidden />
              <span className="sr-only">Close</span>
            </Button>
          </DialogPrimitive.Close>
        ) : null}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export function ModalHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="modal-header"
      className={cn("flex shrink-0 flex-col gap-1 px-4 pt-3 pr-14 pb-4 md:p-6 md:pr-14", className)}
      {...props}
    />
  )
}

/** The only scroll container of a modal; header and footer stay put. */
export function ModalBody({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="modal-body"
      className={cn("min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-4 md:px-6 md:pb-6", className)}
      {...props}
    />
  )
}

export function ModalFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="modal-footer"
      className={cn(
        "flex shrink-0 flex-col-reverse gap-2 border-t px-4 py-4 md:flex-row md:justify-end md:px-6 [&_[data-slot=button]]:w-full md:[&_[data-slot=button]]:w-auto",
        className,
      )}
      {...props}
    />
  )
}

export function ModalTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="modal-title"
      className={cn("type-title-md text-foreground", className)}
      {...props}
    />
  )
}

export function ModalDescription({ className, ...props }: ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="modal-description"
      className={cn("text-body text-muted-foreground", className)}
      {...props}
    />
  )
}
