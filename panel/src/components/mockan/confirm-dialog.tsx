import { AlertDialog as AlertDialogPrimitive } from "radix-ui"
import type { ReactNode } from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

import { ModalHandle, ModalFooter, ModalHeader, modalOverlayClass, modalSurfaceClass } from "./modal"

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: ReactNode
  confirmLabel: string
  cancelLabel?: string
  /** Destructive confirms use the error-toned button, not coral. */
  destructive?: boolean
  pending?: boolean
  onConfirm: () => void
}

/**
 * Confirmation for destructive or risky actions (delete rule/Service/environment, mocks off). An `alertdialog` that
 * a tap outside does not dismiss; it has the Modal's surface: centered ≥ 768 px, a bottom sheet below.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive,
  pending,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogPortal>
        <AlertDialogOverlay className={modalOverlayClass} />
        <AlertDialogPrimitive.Content data-slot="alert-dialog-content" className={modalSurfaceClass("sm")}>
          <ModalHandle />
          <ModalHeader className="pr-4 md:pr-6">
            <AlertDialogTitle className="type-title-md">{title}</AlertDialogTitle>
            <AlertDialogDescription className="text-body">{description}</AlertDialogDescription>
          </ModalHeader>
          <ModalFooter className="border-t-0 pt-0">
            <AlertDialogCancel>{cancelLabel}</AlertDialogCancel>
            <AlertDialogAction
              variant={destructive ? "destructive" : "default"}
              disabled={pending}
              onClick={(event) => {
                event.preventDefault()
                onConfirm()
              }}
            >
              {confirmLabel}
            </AlertDialogAction>
          </ModalFooter>
        </AlertDialogPrimitive.Content>
      </AlertDialogPortal>
    </AlertDialog>
  )
}
