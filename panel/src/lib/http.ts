/** HTTP reason phrases for the status-code presets and response previews. */
export const STATUS_PRESETS = [200, 201, 204, 400, 401, 403, 404, 409, 422, 500, 502, 503] as const

const REASONS: Record<number, string> = {
  100: "Continue",
  200: "OK",
  201: "Created",
  202: "Accepted",
  204: "No Content",
  301: "Moved Permanently",
  302: "Found",
  304: "Not Modified",
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  405: "Method Not Allowed",
  409: "Conflict",
  422: "Unprocessable Content",
  429: "Too Many Requests",
  500: "Internal Server Error",
  502: "Bad Gateway",
  503: "Service Unavailable",
  504: "Gateway Timeout",
}

export const reasonPhrase = (code: number) => REASONS[code] ?? ""

export const DELAY_PRESETS = [
  { ms: 0, label: "0" },
  { ms: 300, label: "300 ms" },
  { ms: 1000, label: "1 s" },
  { ms: 3000, label: "3 s" },
] as const
