/**
 * Dev only (MSW): stands in for the OIDC redirect at `/api/v1/auth/login` (D-12). Vite serves the SPA for
 * that path, so this route completes a simulated SSO login and returns to the Panel.
 */
import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"
import { useNavigate } from "react-router"

import { Wordmark } from "@/components/mockan"
import { simulateLogin } from "@/mocks/handlers/auth"

export function DevLoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  useEffect(() => {
    const timer = window.setTimeout(() => {
      simulateLogin()
      queryClient.clear()
      void navigate("/", { replace: true })
    }, 400)
    return () => window.clearTimeout(timer)
  }, [navigate, queryClient])

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-3">
      <Wordmark />
      <p className="text-body" role="status">
        Signing you in with company SSO…{" "}
        <span className="text-muted-foreground">(simulated by the MSW dev backend)</span>
      </p>
    </main>
  )
}
