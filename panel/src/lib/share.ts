import { PANEL_BASE_PATH } from "@/lib/config"

/** The public, read-only page of a shared rule: `{panel origin}{base path}/shared/{token}` (S-6). */
export const shareUrl = (token: string, origin: string = window.location.origin) =>
  `${origin}${PANEL_BASE_PATH.replace(/\/$/, "")}/shared/${token}`
