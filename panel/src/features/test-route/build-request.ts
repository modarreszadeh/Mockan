import type { HttpMethodOrAny, TestRouteRequest } from "@/api/types"
import type { KeyValueRow } from "@/lib/validation"

/** Group rows into the API's `{name: [values]}` (a repeated name is a repeated parameter). */
function groupQuery(rows: KeyValueRow[]): Record<string, string[]> {
  const query: Record<string, string[]> = {}
  for (const row of rows) if (row.key.trim()) (query[row.key.trim()] ??= []).push(row.value)
  return query
}

/**
 * The path the Developer typed may carry a query string (`/orders?status=pending`); the API wants it separate,
 * so it moves into the query rows instead of being rejected.
 */
export function buildRequest(
  method: HttpMethodOrAny,
  rawPath: string,
  queryRows: KeyValueRow[],
  headerRows: KeyValueRow[],
): TestRouteRequest {
  const [path = "", ...rest] = rawPath.trim().split("?")
  const fromPath = new URLSearchParams(rest.join("?"))
  const rows = [...[...fromPath].map(([key, value]) => ({ key, operator: "equals" as const, value })), ...queryRows]
  const headers: Record<string, string> = {}
  for (const row of headerRows) if (row.key.trim()) headers[row.key.trim()] = row.value
  return { method, path, query: groupQuery(rows), headers }
}
