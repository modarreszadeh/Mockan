/**
 * Auth guard (prompt §5): loads `GET /me`. 401 → the client already navigated to SSO login. Disabled Developer →
 * full-page explanation. No slug → every route except /onboarding redirects there.
 */
import { Navigate, Outlet, useLocation } from "react-router"

import { ApiError } from "@/api/client"
import { useMe } from "@/api/queries/me"

import { DisabledPage, ForbiddenPage, FullPageLoading, LoadFailedPage } from "./system-pages"

export function AuthGate() {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) return <FullPageLoading />
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) return <FullPageLoading />
    return <LoadFailedPage error={me.error} onRetry={() => void me.refetch()} />
  }

  const developer = me.data
  if (!developer.isEnabled) return <DisabledPage slug={developer.slug} />
  if (!developer.slug && location.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />
  return <Outlet />
}

/** `/admin/*`: non-admins see a 403 page (SCR-07). */
export function AdminGate() {
  const me = useMe()
  if (!me.data?.isAdmin) return <ForbiddenPage />
  return <Outlet />
}
