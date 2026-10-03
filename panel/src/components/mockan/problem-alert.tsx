import { AlertCircleIcon, RotateCwIcon } from "lucide-react"

import { ApiError } from "@/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface ProblemAlertProps {
  error: unknown
  /** Shown as a retry button when given. */
  onRetry?: () => void
  className?: string
}

/** Renders an RFC 7807 problem+json: `title`, `detail`, and `code` in mono. */
export function ProblemAlert({ error, onRetry, className }: ProblemAlertProps) {
  const problem =
    error instanceof ApiError
      ? error.problem
      : { title: "Something went wrong", detail: error instanceof Error ? error.message : undefined }
  const detail = typeof problem.detail === "string" ? problem.detail : undefined
  const code = typeof problem.code === "string" ? problem.code : undefined

  return (
    <Alert role="alert" className={cn("border-error/40 bg-canvas *:[svg]:text-error", className)}>
      <AlertCircleIcon aria-hidden />
      <AlertTitle className="text-ink">{problem.title ?? "Something went wrong"}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-2 text-body">
        {detail ? <p>{detail}</p> : null}
        {code ? (
          <p>
            Code: <code className="font-mono text-[13px] text-ink">{code}</code>
          </p>
        ) : null}
        {onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
            <RotateCwIcon aria-hidden />
            Try again
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}
