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
  }
}

export default defineConfig(createViteConfig)
