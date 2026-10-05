/** Build-time configuration read from `import.meta.env` (documented in Frontend/README.md). */

/** Fallback only: the Panel shows `publicBaseUrl` from `GET /me` (OQ-F4) and uses this until it has loaded. */
export const PUBLIC_BASE_URL = (import.meta.env.VITE_MOCKAN_PUBLIC_BASE_URL || "https://mock.novin-tools.com").replace(
  /\/+$/,
  "",
)

// TODO(OQ-03): Panel at `/_mockan/admin` or on a separate host.
export const PANEL_BASE_PATH = import.meta.env.BASE_URL

/**
 * MSW mock backend: on by default in `npm run dev`, off in production builds. `VITE_USE_MSW=false` uses the
 * real Admin API in dev; `VITE_USE_MSW=true` bundles MSW into a build (demo / e2e against `vite preview`).
 */
export const USE_MSW = import.meta.env.VITE_USE_MSW ? import.meta.env.VITE_USE_MSW !== "false" : import.meta.env.DEV

/** Default AllowedOrigins (MOCKAN_DEFAULT_ALLOWED_ORIGINS, arch §12.3). */
export const DEFAULT_ALLOWED_ORIGINS: readonly string[] = ["http://localhost:*", "http://127.0.0.1:*"]
