/** Query key factories — one per resource (prompt §6). Mutations invalidate exactly these keys. */
export const meKeys = {
  all: ["me"] as const,
}

export const ruleKeys = {
  all: ["rules"] as const,
  list: () => [...ruleKeys.all, "list"] as const,
  detail: (ruleId: string) => [...ruleKeys.all, "detail", ruleId] as const,
}

export const serviceKeys = {
  all: ["services"] as const,
  list: () => [...serviceKeys.all, "list"] as const,
}

export const serviceSettingKeys = {
  all: ["service-settings"] as const,
}

export const logKeys = {
  all: ["request-logs"] as const,
  list: (filters: { source?: string; path?: string }) => [...logKeys.all, "list", filters] as const,
}
