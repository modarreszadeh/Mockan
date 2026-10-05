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
| E2E | Playwright | `e2e/journey.spec.ts`, `e2e/phase2.spec.ts`, `e2e/overlays.spec.ts` | The PRD §6 journey: first login → claim slug → copy base URL → create Exact `GET /limsa/api/v1/dashboard` with JSON → see it in Rules and Overview → disable it → kill switch on/off. Phase 2: a live entry arrives, Mock this, a scenario duplicated and made active, Test route confirms it, export downloads a file. All run on MSW. `overlays.spec.ts` runs in both Playwright projects, `chromium` (1440 × 900) and `mobile` (390 × 844, touch), and checks that every overlay is centered at ≥ 768 px and a full-width bottom sheet below, and that resizing keeps an open form. |

Name tests after requirement IDs where they apply, e.g. `PR-05 template pattern rejects {*rest} in the middle`.

## MSW dev backend

`src/mocks/` implements every Admin API route the Panel calls (arch §10) with the §10 validation rules and problem+json errors.

| File | Contents |
| --- | --- |
| `fixtures.ts` | Developer `ehtesham` (admin), Services `identity`, `limsa`, `portal` (portal has only `stage`), 6 rules incl. the PRD §6 dashboard rule, taken slugs (`qoolak`, `sara`, `admin-team`), upstream allowlist. |
| `db.ts` | In-memory state; persisted to `sessionStorage` in the browser. |
| `handlers/` | `auth`, `me`, `services` (catalog + service settings), `rules` (incl. scenarios), `transfer` (export/import: validates the whole file, all or nothing), `logs` (history with cursor and filters, Mock this), `test-route`. Rule validation errors use FastAPI's `422 detail[]`; others use problem+json `errors` (exercises both OQ-F1 shapes). `rules/export` and `rules/import` are listed before `rules/:ruleId`. |
| `matching.ts` | A small stand-in for the Gateway decision behind `POST /me/test-route` (precedence, conditions, Service by prefix, selected environment). Its `reason` texts copy the real server's. It is not the real matcher: the real one is proven by `server/tests/admin/test_admin_to_gateway.py`. |
| `live-log.ts` | Simulated `/hubs/request-log` (MSW `ws`), browser only: pushes a made-up request every 4 s while the Live log is open. Not in `handlers`, so Vitest never opens it; log tests use `src/test/fake-socket.ts` instead. |
| `browser.ts` / `server.ts` | Worker for `npm run dev`; Node server for Vitest (`onUnhandledRequest: "error"`). |

### MSW scenarios

Append `?mswScenario=<name>` to any dev URL to reset the mock db. Tests call `resetDb(name)`.

| Scenario | State |
| --- | --- |
| `default` | Signed in as `ehtesham` (admin) with rules; `limsa` on `dev`. |
| `new` | Signed out, no slug, no rules — the first-login journey (the login page, then SSO simulated by the dev-only `/api/v1/auth/login` route). |
| `empty` | Slug claimed, no rules. |
| `member` | Non-admin Developer. |
| `disabled` | Disabled Developer. |
| `broken` | Every read returns `500` problem+json. |

## Checking against the real backend

MSW can drift from the server, so after changing anything under `src/api/`, run the Panel against the real Admin and Gateway ([README](README.md#running-against-the-real-backend)) and walk the affected screens. The M5 check covered, with real traffic through the Gateway: log history and a live entry over the WebSocket, masked headers in the details modal, Mock this, duplicating a scenario and making it active (the Gateway answered `200` before and `503` after), a Template body rendered by the Gateway, Test route (mock and proxy), and export, then replace-import, then a bad file that left the rules untouched. Do it with the **production build** served by the Admin as well (`npm run build:server`): it has no MSW and the WebSocket is same-origin.

Notes for a local machine: the compose Postgres wants port 5432 (set `MOCKAN_DB_PORT`); the Playwright MCP wants system Chrome, so drive the browser from a Node script with `playwright-core` (`npx playwright install chromium`, through the proxy if needed); don't `pkill -f` a pattern that your own command line contains.

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
