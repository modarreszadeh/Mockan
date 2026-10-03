---
title: Mockan Panel — Testing
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - conventions.md
  - ../Agent/mockan-architecture.md
---

# Mockan Panel — Testing

> **Summary:** test layers, the MSW dev backend (fixtures and scenarios), the accessibility gate and how to run everything.

## Layers

| Layer | Tool | Location | What MUST be covered |
| --- | --- | --- | --- |
| Unit | Vitest | `src/lib/*.test.ts`, `src/api/*.test.ts` | zod schemas vs arch §10 (slugs, patterns, status codes, delays, body size), precedence sort (§7.2), field-error mapping (OQ-F1). |
| Component | Vitest + Testing Library | `src/components/mockan/*.test.tsx` | Every domain component's states. |
| Screen | Vitest + Testing Library + MSW (Node) | `src/features/<x>/*.test.tsx`, `src/app/*.test.tsx` | Loading / empty / error / success per screen; acceptance criteria from [screens.md](screens.md). |
| Accessibility | `vitest-axe` | in component and screen tests | `expect(await axe(container)).toHaveNoViolations()` on every screen in its success **and** empty state. `color-contrast` is checked by hand (jsdom has no layout) — see design-tokens.md §4. |
| E2E | Playwright | `e2e/` | The PRD §6 journey. |

Name tests after requirement IDs where they apply, e.g. `PR-05 template pattern rejects {*rest} in the middle`.

## MSW dev backend

`src/mocks/` implements every Admin API route the Panel calls (arch §10) with the §10 validation rules and problem+json errors.

| File | Contents |
| --- | --- |
| `fixtures.ts` | Developer `ehtesham` (admin), Services `identity`, `limsa`, `portal` (portal has only `stage`), 6 rules incl. the PRD §6 dashboard rule, taken slugs (`qoolak`, `sara`, `admin-team`), upstream allowlist. |
| `db.ts` | In-memory state; persisted to `sessionStorage` in the browser. |
| `handlers/` | `auth`, `me`, `services` (catalog + service settings), `rules`. Rule validation errors use FastAPI's `422 detail[]`; others use problem+json `errors` (exercises both OQ-F1 shapes). |
| `browser.ts` / `server.ts` | Worker for `npm run dev`; Node server for Vitest (`onUnhandledRequest: "error"`). |

### MSW scenarios

Append `?mswScenario=<name>` to any dev URL to reset the mock db. Tests call `resetDb(name)`.

| Scenario | State |
| --- | --- |
| `default` | Signed in as `ehtesham` (admin) with rules; `limsa` on `dev`. |
| `new` | Signed out, no slug, no rules — the first-login journey (SSO is simulated by the dev-only `/api/v1/auth/login` route). |
| `empty` | Slug claimed, no rules. |
| `member` | Non-admin Developer. |
| `disabled` | Disabled Developer. |
| `broken` | Every read returns `500` problem+json. |

## Running

```bash
npm test                 # all Vitest tests
npm run test:watch
npm run e2e              # Playwright
npm run check            # milestone gate: typecheck + lint + test + build
```

### E2E browser

Playwright's browser download (`npx playwright install chromium`) may be blocked on some networks. `playwright.config.ts` uses `PLAYWRIGHT_CHROMIUM_PATH` when set, e.g. a locally installed Chromium-based browser:

```bash
PLAYWRIGHT_CHROMIUM_PATH=/snap/bin/brave npm run e2e
```
