/** `/auth/*` — the SSO flow is simulated: login is handled by the dev-only DevLogin route. */
import { http, HttpResponse } from "msw"

import { db, persist } from "../db"

export const authHandlers = [
  http.post("*/api/v1/auth/logout", () => {
    db.signedIn = false
    persist()
    return new HttpResponse(null, { status: 204 })
  }),
]

/** Called by the dev-only `/api/v1/auth/login` route to complete the simulated SSO login. */
export function simulateLogin() {
  db.signedIn = true
  persist()
}
