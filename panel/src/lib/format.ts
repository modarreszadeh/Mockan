/** Formatting helpers shared by screens. */
export const developerBaseUrl = (publicBaseUrl: string, slug: string) => `${publicBaseUrl.replace(/\/+$/, "")}/${slug}`

/** The `.env` line shown in BaseUrlCard (arch §11). */
export const envLine = (publicBaseUrl: string, slug: string) =>
  `VITE_API_BASE_URL=${developerBaseUrl(publicBaseUrl, slug)}`

const relativeFormatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" })
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
]

export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000)
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relativeFormatter.format(Math.round(seconds / size), unit)
  }
  return "just now"
}

export const absoluteTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })

export function greeting(date: Date = new Date()): string {
  const hour = date.getHours()
  if (hour < 5) return "Good evening"
  if (hour < 12) return "Good morning"
  if (hour < 18) return "Good afternoon"
  return "Good evening"
}

export const formatDelay = (ms: number) =>
  ms === 0
    ? "no delay"
    : ms < 1000
      ? `${ms} ms`
      : `${(ms / 1000).toLocaleString("en-US", { maximumFractionDigits: 2 })} s`

export const formatBytes = (bytes: number) =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / 1024 / 1024).toFixed(2)} MB`

export const pluralize = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`

/** Convert `{ key: value }` to KeyValueEditor rows and back. */
export const recordToRows = (record: Record<string, string>) =>
  Object.entries(record).map(([key, value]) => ({ key, operator: "equals" as const, value }))

export const rowsToRecord = (rows: readonly { key: string; value: string }[]) =>
  Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value]))

/** Time of day for log rows (`14:03:22`), with the date when it isn't today. */
export function logTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso)
  const time = date.toLocaleTimeString("en-GB", { hour12: false })
  return date.toDateString() === now.toDateString()
    ? time
    : `${date.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${time}`
}

/** `Name: value` lines for a header map, for CodeBlock. */
export const headersText = (headers: Record<string, string>) =>
  Object.entries(headers)
    .map(([name, value]) => `${name}: ${value}`)
    .join("\n")

/** A captured body sample, pretty-printed when it is JSON (a sample cut off mid-way stays as it is). */
export function formatSample(sample: string): string {
  try {
    return JSON.stringify(JSON.parse(sample), null, 2)
  } catch {
    return sample
  }
}
