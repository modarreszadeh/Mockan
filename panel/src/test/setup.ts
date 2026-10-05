/** Vitest setup: DOM matchers, axe matcher, MSW server with a fresh db per test, jsdom polyfills. */
import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, beforeEach, expect, vi } from "vitest"
import * as axeMatchers from "vitest-axe/matchers"

import { resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"

expect.extend(axeMatchers)

// Monaco can't run in jsdom: swap the lazy editor surface for a textarea with the same props.
vi.mock("@/components/mockan/monaco-surface", async () => {
  const { createElement } = await import("react")
  return {
    default: ({ id, value, onChange, onBlur, label, describedBy }: Record<string, unknown>) =>
      createElement("textarea", {
        id,
        "aria-label": label,
        "aria-describedby": describedBy,
        "data-testid": "json-editor",
        value,
        onChange: (e: { target: { value: string } }) => (onChange as (v: string) => void)(e.target.value),
        onBlur,
      }),
  }
})

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
beforeEach(() => resetDb("default"))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())

// --- jsdom polyfills used by Radix / shadcn ---
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("min-width: 1024px"),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver

Element.prototype.scrollIntoView ??= () => undefined
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => undefined
Element.prototype.setPointerCapture ??= () => undefined

Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: { writeText: vi.fn(() => Promise.resolve()) },
})
