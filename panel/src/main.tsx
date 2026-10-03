import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "@/styles/globals.css"

import { App } from "@/app/app"

async function start() {
  // Inlined (not USE_MSW from lib/config) so production builds tree-shake MSW away. Same rule as USE_MSW.
  const useMsw = import.meta.env.DEV
    ? import.meta.env.VITE_USE_MSW !== "false"
    : import.meta.env.VITE_USE_MSW === "true"
  if (useMsw) {
    const { startMockBackend } = await import("@/mocks/browser")
    await startMockBackend()
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void start()
