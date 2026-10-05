---
title: Mockan Frontend (Panel) — Documentation index
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - ../agent/mockan-architecture.md
  - ../product/mockan-prd.md
  - ../agent/prompts/panel-dashboard.md
  - ../product/design/shadcn-design.md
audience: Frontend engineers and AI coding agents working in `panel/`
---

# Mockan Frontend (Panel) — Documentation index

> **What this folder covers:** how the Mockan Panel (the React SPA where a Developer claims a workspace, picks environments and creates MockRules) is built: stack, folder layout, design tokens, components, screens, conventions and testing. **What** the product does is in the [PRD](../product/mockan-prd.md); the system contract (glossary, data model, Admin API) is in the [architecture](../agent/mockan-architecture.md). The build brief is [`docs/agent/prompts/panel-dashboard.md`](../agent/prompts/panel-dashboard.md).

## Quick facts

| Item | Value |
| --- | --- |
| App | React 19 + TypeScript (strict) SPA, built with Vite 8 (D-11) |
| Code location | `panel/` → build output copied to `server/src/mockan/admin/static/` (`npm run build:server`) |
| UI kit | shadcn/ui (Radix) + Tailwind CSS v4, re-themed with tokens in `panel/src/styles/globals.css` |
| Server state | TanStack Query; forms with react-hook-form + zod |
| Bundle | Initial JS ≈ 184 KB gzip (budget 250 KB); Monaco and every screen are lazy-loaded |
| API | Admin API at `/api/v1` (arch §10, contract in [admin-api.md](../backend/admin-api.md)), cookie session; live log over the WebSocket `/hubs/request-log`; dev defaults to MSW handlers in `panel/src/mocks/` |
| Phase | **Phase 1 (M0–M4) and Phase 2 (M5) built**, and checked against the real Admin API and Gateway (see [Running against the real backend](#running-against-the-real-backend)). |

## Quick start

```bash
cd panel
npm ci
npm run dev              # http://localhost:5173 with the MSW mock backend
npm run check            # typecheck + lint + unit/component tests + build
npm run e2e              # Playwright PRD §6 journey (needs a Chromium, see testing.md)
```

### Running against the real backend

The Admin serves the Panel and the API on one origin, so the session cookie just works.

```bash
# 1. Postgres, Admin (:8081) and a Gateway: see ../backend/operations.md §1 (compose) or the Backend quick start.
# 2a. Develop the Panel against it (Vite proxies /api and /hubs, WebSocket included):
cd panel && VITE_USE_MSW=false MOCKAN_ADMIN_URL=http://localhost:8081 npm run dev
# 2b. Or serve the production build from the Admin itself:
npm run build:server        # copies dist/ to server/src/mockan/admin/static/ (git-ignored); restart the Admin once
```

Dev sign-in (`MOCKAN_AUTH_MODE=dev`) logs in as `dev:dev`; the compose file makes that user an admin. A request that goes **through the Gateway** is what fills the Live log: send one with `curl http://localhost:8765/mock/<slug>/<service-prefix>/...`.

Open `http://localhost:5173/__design` (dev only) for the living style guide. Append `?mswScenario=new` to any URL to start as a brand-new Developer (see [testing.md](testing.md#msw-scenarios)).

## Configuration (build-time env)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_PANEL_BASE_PATH` | `/` | Vite `base` and router basename. `TODO(OQ-03)` |
| `VITE_MOCKAN_PUBLIC_BASE_URL` | `https://mock.novin-tools.com` | Fallback for the base URL / `.env` snippet; the real value is `publicBaseUrl` from `GET /me` (OQ-F4). |
| `VITE_USE_MSW` | dev: on · build: off | `false` in dev → real Admin API; `true` in a build → bundle MSW (demo / e2e). |
| `MOCKAN_ADMIN_URL` | `http://localhost:8081` | Dev server only (with `VITE_USE_MSW=false`): where `/api` and `/hubs` are proxied. |

## Documents

| File | Topic | Status |
| --- | --- | --- |
| [tech-stack.md](tech-stack.md) | Libraries, pinned versions, why. | Draft |
| [project-structure.md](project-structure.md) | `panel/` tree, import rules, scripts. | Draft |
| [design-tokens.md](design-tokens.md) | Token table, shadcn mapping, contrast results, deviations from the design file. | Draft |
| [components.md](components.md) | Mockan domain components: props, states, usage. | Draft |
| [screens.md](screens.md) | SCR-02 … SCR-10: route, data, states, acceptance criteria. | Draft |
| [conventions.md](conventions.md) | Naming, feature layout, query keys, errors, copy. | Draft |
| [testing.md](testing.md) | Test layers, MSW fixtures and scenarios, a11y gate, e2e. | Draft |
| [plan-responsive-overlays.md](plan-responsive-overlays.md) | Plan (breaking): every Sheet/Dialog becomes a modal ≥ 768 px and a bottom sheet < 768 px. | Implemented |

## Open questions

IDs are stable and never renumbered. Defaults are implemented with a `TODO(OQ-xx)` marker at the exact spot.

| ID | Question | Default implemented | Marker locations |
| --- | --- | --- | --- |
| OQ-03 | Panel at `/_mockan/admin` or a separate host? | Vite `base` + router basename from `VITE_PANEL_BASE_PATH`, default `/`. | `vite.config.ts`, `src/app/router.tsx`, `src/lib/config.ts` |
| OQ-P1 | Which phase ships scenario-switching UI? **Resolved:** Phase 2 (M5), built. | Scenario tabs with "Make active" in the rule editor (SCR-05). | `src/features/rules/scenario-bar.tsx`, `src/features/rules/rule-editor-page.tsx` |
| OQ-F1 | What shape do Admin API validation errors take? **Resolved (backend G-1):** `422` problem+json with `errors: {"<camelCase.dotted.path>": [msg]}` ([admin-api.md §5](../backend/admin-api.md#5-errors)). | The Panel still parses both shapes; the FastAPI `detail[]` branch is now only a fallback. | `src/api/client.ts`, `src/api/types.ts` |
| OQ-F2 | Dark theme? | Light only in v1; every colour is a token so a `.dark` block can be added. | `src/styles/globals.css`, `src/components/ui/sonner.tsx` |
| OQ-F3 | Is white-on-coral (3.28:1) acceptable for primary buttons? | Keep brand coral; switch the fill to `primary-active` (5.06:1) if rejected. | `src/styles/globals.css`, `src/components/ui/button.tsx` |
| OQ-F4 | Where does the Panel get `MOCKAN_PUBLIC_BASE_URL`? **Resolved (backend G-4) and implemented:** `GET /me` returns a read-only `publicBaseUrl`. | `usePublicBaseUrl()` (`src/api/queries/me.ts`) reads it; `VITE_MOCKAN_PUBLIC_BASE_URL` is only the fallback until `GET /me` has loaded. | `src/lib/config.ts`, `src/api/queries/me.ts` |
| OQ-F5 | Admin API payload shapes (arch §10 lists routes, not bodies). **Resolved (backend G-2):** the shapes below are the contract, documented in [admin-api.md](../backend/admin-api.md) and pinned by `server/tests/admin/openapi.snapshot.json`. | Phase 2 payloads (request log, test route, export/import) are in `src/api/types.ts`. Change `types.ts` in the same commit as the OpenAPI snapshot. | `src/api/types.ts`, `src/api/queries/*.ts`, `src/mocks/handlers/*.ts` |
| OQ-F6 | Monaco throws `[createInstance] … depends on UNKNOWN service ICodeLensCache` (uncaught, harmless: the editor keeps working) in the **production build** every time a second editor is mounted in one session (open a rule, go back, open another). Present since M3; not in `npm run dev`. | Deferred as its own task (the cause is in how Rolldown chunks `monaco-editor`, not in Panel code). The scenario tabs avoid it by not remounting the editor. Look at how Rolldown splits the service registrations of `monaco-editor` (the `jsonMode` chunk) before changing imports. | `src/components/mockan/monaco-surface.tsx` |
| OQ-F7 | Should the mobile sidebar (left `Sheet` < 768 px) also become a bottom sheet? | No: it is navigation, it stays a left drawer. | `src/components/ui/sidebar.tsx` |
| OQ-F8 | Should `Select` / `DropdownMenu` open as bottom sheets on mobile? | No: they stay anchored popovers. | `src/components/ui/select.tsx`, `dropdown-menu.tsx` |
| OQ-F9 | Is drag-to-dismiss on the bottom sheet required? | No: X, Esc, tap outside and Cancel only; the grab handle is decorative. | `src/components/mockan/modal.tsx` |

### OQ-F5 assumed payloads

| Route | Assumed shape |
| --- | --- |
| `GET /me/rules`, `GET /me/rules/{id}` | `MockRule` embeds `responses: MockResponse[]` and `activeResponseId`. |
| `POST /me/rules` | Rule fields + `responses: MockResponseInput[]`; the first one becomes active. Returns the full `MockRule`. |
| `PUT /me/rules/{id}` | Rule fields only (no responses). Responses are saved with `PUT /me/rules/{id}/responses/{responseId}`. |
| `POST /me/rules/{id}/toggle`, `POST /me/rules/toggle-all` | Body `{ "isEnabled": boolean }` (idempotent). `toggle-all` returns `{ "updated": n }`. |
| `GET/PUT /me/service-settings` | `DeveloperServiceSetting[]` = `[{ serviceId, serviceEnvironmentId }]`; PUT replaces the whole set; a missing Service = its default environment. |
| `GET /me` | `Developer` incl. `isEnabled`, `isAdmin`; `isEnabled: false` → full-page "workspace disabled". |
| `DELETE /me/rules/{id}/responses/{responseId}` | Deleting the rule's **last** response → `409 last_response` (a rule always has an active response, G-3). The MSW handler does the same. |
| Catalog errors | Upstream host not allowed → `422` with `code: upstream_host_not_allowed` and a `baseUrl` field error. |
