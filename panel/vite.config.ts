import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv, type ConfigEnv, type UserConfig } from "vite"

// https://vite.dev/config/
export const createViteConfig = ({ mode }: ConfigEnv): UserConfig => {
  const env = loadEnv(mode, process.cwd(), "")
  return {
    // TODO(OQ-03): Panel host/path is undecided; base comes from VITE_PANEL_BASE_PATH (default "/").
    base: env.VITE_PANEL_BASE_PATH || "/",
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(import.meta.dirname, "./src") },
    },
    // `VITE_USE_MSW=false`: talk to the real Admin API (`uv run uvicorn mockan.admin.app:create_app
    // --factory --port 8081`) through the dev server, so the session cookie stays same-origin.
    // MOCKAN_ADMIN_URL overrides the target (e.g. the compose stack on another port).
    server:
      env.VITE_USE_MSW === "false"
        ? {
            proxy: Object.fromEntries(
              ["/api", "/hubs"].map((prefix) => [
                prefix,
                { target: env.MOCKAN_ADMIN_URL || "http://localhost:8081", ws: true },
              ]),
            ),
          }
        : {},
  }
}

export default defineConfig(createViteConfig)
