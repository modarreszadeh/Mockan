/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PANEL_BASE_PATH?: string
  readonly VITE_MOCKAN_PUBLIC_BASE_URL?: string
  readonly VITE_USE_MSW?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
