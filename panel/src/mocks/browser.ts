/** Starts MSW in the browser (dev default; `VITE_USE_MSW=false` uses the real Admin API). */
import { setupWorker } from "msw/browser"

import { isScenario, resetDb } from "./db"
import { handlers } from "./handlers"
import { liveLogHandlers } from "./live-log"

export async function startMockBackend() {
  const params = new URLSearchParams(window.location.search)
  const scenario = params.get("mswScenario")
  if (scenario && isScenario(scenario)) {
    resetDb(scenario)
    params.delete("mswScenario")
    const query = params.toString()
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
    )
  }
  const worker = setupWorker(...handlers, ...liveLogHandlers)
  await worker.start({
    onUnhandledRequest: "bypass",
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
    quiet: true,
  })
}
