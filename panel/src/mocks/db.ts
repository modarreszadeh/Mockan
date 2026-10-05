/**
 * In-memory Admin API state for MSW. In the browser it is persisted to sessionStorage so a reload keeps
 * your changes; `?mswScenario=<name>` resets it to a named scenario (see docs/frontend/testing.md).
 */
import type { Developer, DeveloperServiceSetting, MockRule, RequestLogEntry, Service } from "@/api/types"

import { developerFixture, logsFixture, rulesFixture, serviceSettingsFixture, servicesFixture } from "./fixtures"

export interface MockDb {
  signedIn: boolean
  /** Make every GET fail with 500 — exercises error states. */
  failReads: boolean
  developer: Developer
  services: Service[]
  serviceSettings: DeveloperServiceSetting[]
  rules: MockRule[]
  /** The request log, newest first (PR-12). */
  logs: RequestLogEntry[]
}

export const SCENARIOS = {
  /** Returning Developer with rules (default). */
  default: (): MockDb => ({
    signedIn: true,
    failReads: false,
    developer: developerFixture(),
    services: servicesFixture(),
    serviceSettings: serviceSettingsFixture(),
    rules: rulesFixture(),
    logs: logsFixture(),
  }),
  /** First login: signed out, no slug, no rules (PRD §6 journey). */
  new: (): MockDb => ({
    signedIn: false,
    failReads: false,
    developer: developerFixture({ slug: null, displayName: "Ehtesham", isAdmin: false }),
    services: servicesFixture(),
    serviceSettings: [],
    rules: [],
    logs: [],
  }),
  /** Slug claimed, no rules and no traffic yet. */
  empty: (): MockDb => ({ ...SCENARIOS.default(), rules: [], serviceSettings: [], logs: [] }),
  /** Non-admin Developer. */
  member: (): MockDb => ({ ...SCENARIOS.default(), developer: developerFixture({ isAdmin: false }) }),
  /** Disabled Developer. */
  disabled: (): MockDb => ({ ...SCENARIOS.default(), developer: developerFixture({ isEnabled: false }) }),
  /** Every read fails. */
  broken: (): MockDb => ({ ...SCENARIOS.default(), failReads: true }),
} satisfies Record<string, () => MockDb>

export type ScenarioName = keyof typeof SCENARIOS

const STORAGE_KEY = "mockan.msw.db"
const canPersist = typeof window !== "undefined" && typeof sessionStorage !== "undefined"

function load(): MockDb {
  if (canPersist) {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      if (raw) return { ...SCENARIOS.default(), ...(JSON.parse(raw) as Partial<MockDb>) }
    } catch {
      // Ignore — fall back to the default scenario.
    }
  }
  return SCENARIOS.default()
}

export let db: MockDb = load()

export function persist() {
  if (!canPersist) return
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(db))
  } catch {
    // Storage full or blocked — state stays in memory only.
  }
}

export function resetDb(scenario: ScenarioName = "default") {
  db = SCENARIOS[scenario]()
  persist()
}

export const isScenario = (name: string): name is ScenarioName => name in SCENARIOS
