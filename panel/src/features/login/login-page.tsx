/**
 * SCR-01 Login: the page every 401 and "Sign out" lead to. One way in: single sign-on through Keycloak
 * (D-12, OQ-04); Mockan has no passwords of its own. The button is a plain link to the Admin's
 * `/api/v1/auth/login`, which redirects to the identity provider.
 */
import { KeyRoundIcon, Loader2Icon } from "lucide-react"
import { useEffect, useState, type MouseEvent } from "react"
import { Navigate } from "react-router"

import { LOGIN_URL } from "@/api/client"
import { useMe } from "@/api/queries/me"
import { LogoMark, Wordmark } from "@/components/mockan"
import { Button } from "@/components/ui/button"

/** The identity provider's name as users know it. One place, so a provider change is one edit. */
const SSO_PROVIDER = "Keycloak"

export function LoginPage() {
  const me = useMe()
  const [redirecting, setRedirecting] = useState(false)

  // Coming back with the browser's Back button restores this page from the cache: undo "Redirecting…".
  useEffect(() => {
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) setRedirecting(false)
    }
    window.addEventListener("pageshow", onShow)
    return () => window.removeEventListener("pageshow", onShow)
  }, [])

  // Already signed in (a bookmark, or Back after login): nothing to do here.
  if (me.isSuccess) return <Navigate to="/" replace />

  const start = (event: MouseEvent<HTMLAnchorElement>) => {
    if (redirecting)
      event.preventDefault() // a second click must not start a second login
    else setRedirecting(true)
  }

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background px-4 py-10">
      <div className="flex flex-col items-center gap-4">
        <LogoMark className="size-16" />
        <Wordmark />
      </div>
      <section
        aria-labelledby="login-title"
        className="w-full max-w-sm space-y-6 rounded-2xl bg-card p-6 ring-1 ring-border sm:p-8"
      >
        <div className="space-y-2">
          <h1 id="login-title" className="type-display-sm text-ink">
            Sign in to Mockan
          </h1>
          <p className="text-body text-muted-foreground">
            Use your company account to open your workspace. Mocks stay yours; everything else goes to the real backend.
          </p>
        </div>

        <div className="space-y-3">
          <Button
            asChild
            size="lg"
            className="w-full"
            aria-disabled={redirecting || undefined}
            data-redirecting={redirecting || undefined}
          >
            <a href={LOGIN_URL} onClick={start} autoFocus>
              {redirecting ? (
                <Loader2Icon aria-hidden className="motion-safe:animate-spin" />
              ) : (
                <KeyRoundIcon aria-hidden />
              )}
              {redirecting ? `Redirecting to ${SSO_PROVIDER}…` : `Sign in with ${SSO_PROVIDER}`}
            </a>
          </Button>
          <p
            className="text-center type-caption font-normal text-muted-foreground"
            role={redirecting ? "status" : undefined}
          >
            Single sign-on. You'll go to {SSO_PROVIDER} and come back here; Mockan never sees your password.
          </p>
        </div>
      </section>
    </main>
  )
}
