/** Full-page states outside the normal screens: loading, disabled workspace, 403, 404, crash, simulated SSO. */
import { LockIcon, OctagonAlertIcon, SearchXIcon, UserXIcon, type LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { Link, isRouteErrorResponse, useRouteError } from "react-router"

import { ProblemAlert, Wordmark } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useLogout } from "@/api/queries/me"

export function FullPageLoading() {
  return (
    <div className="flex min-h-svh" role="status" aria-busy="true" aria-label="Loading Mockan">
      <div className="hidden w-64 shrink-0 space-y-3 bg-sidebar p-4 md:block">
        <Skeleton className="h-7 w-28 bg-surface-card" />
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full bg-surface-card" />
        ))}
      </div>
      <div className="flex-1 space-y-6 p-8">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-28 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      </div>
    </div>
  )
}

function SystemPage({
  icon: Icon,
  title,
  children,
  actions,
}: {
  icon: LucideIcon
  title: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <main className="mx-auto flex min-h-[60svh] max-w-xl flex-col justify-center gap-4 px-4 py-12">
      <Icon aria-hidden className="size-6 text-ink" strokeWidth={1.75} />
      <h1 className="type-display-sm text-ink">{title}</h1>
      <div className="space-y-2 text-body">{children}</div>
      {actions ? <div className="mt-2 flex flex-wrap gap-2">{actions}</div> : null}
    </main>
  )
}

/** A disabled Developer sees this instead of the app (prompt §5 auth guard). */
export function DisabledPage({ slug }: { slug: string | null }) {
  const logout = useLogout()
  return (
    <div className="min-h-svh">
      <header className="px-6 py-5">
        <Wordmark />
      </header>
      <SystemPage
        icon={UserXIcon}
        title="Your workspace is disabled"
        actions={
          <Button variant="outline" onClick={() => logout.mutate()}>
            Sign out
          </Button>
        }
      >
        <p>
          A Mockan admin disabled the workspace
          {slug ? (
            <>
              {" "}
              <code className="font-mono text-ink">{slug}</code>
            </>
          ) : null}
          . Requests to its base URL return <code className="font-mono text-ink">developer_not_found</code> and the
          Panel is read-only for you.
        </p>
        <p>Ask a Mockan admin to re-enable it.</p>
      </SystemPage>
    </div>
  )
}

export function ForbiddenPage() {
  return (
    <SystemPage
      icon={LockIcon}
      title="Admins only"
      actions={
        <Button asChild variant="outline">
          <Link to="/services">Go to Services</Link>
        </Button>
      }
    >
      <p>Only Mockan admins can change the Service catalog. You can still pick an environment per Service.</p>
    </SystemPage>
  )
}

export function NotFoundPage() {
  return (
    <SystemPage
      icon={SearchXIcon}
      title="Page not found"
      actions={
        <Button asChild variant="outline">
          <Link to="/">Go to overview</Link>
        </Button>
      }
    >
      <p>This page doesn't exist. Check the address or go back to the overview.</p>
    </SystemPage>
  )
}

export function LoadFailedPage({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="min-h-svh">
      <header className="px-6 py-5">
        <Wordmark />
      </header>
      <main className="mx-auto max-w-xl px-4 py-12">
        <ProblemAlert error={error} onRetry={onRetry} />
      </main>
    </div>
  )
}

/** Route `errorElement`: an unexpected crash, never a blank page. */
export function RouteErrorPage() {
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />
  return (
    <SystemPage
      icon={OctagonAlertIcon}
      title="Something broke"
      actions={<Button onClick={() => window.location.reload()}>Reload</Button>}
    >
      <p>The Panel hit an unexpected error. Reload the page; if it keeps happening, tell the Mockan team.</p>
    </SystemPage>
  )
}
