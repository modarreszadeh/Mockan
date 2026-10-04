---
title: Mockan Frontend (Panel) — Documentation index
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - ../Agent/mockan-architecture.md
  - ../Product/mockan-prd.md
  - ../Agent/prompts/panel-dashboard.md
  - ../Product/Design/shadcn-design.md
audience: Frontend engineers and AI coding agents working in `panel/`
---

# Mockan Frontend (Panel) — Documentation index

> **What this folder covers:** how the Mockan Panel (the React SPA where a Developer claims a workspace, picks environments and creates MockRules) is built: stack, folder layout, design tokens, components, screens, conventions and testing. **What** the product does is in the [PRD](../Product/mockan-prd.md); the system contract (glossary, data model, Admin API) is in the [architecture](../Agent/mockan-architecture.md). The build brief is [`Agent/prompts/panel-dashboard.md`](../Agent/prompts/panel-dashboard.md).

## Quick facts

| Item | Value |
| --- | --- |
| App | React 19 + TypeScript (strict) SPA, built with Vite 8 (D-11) |
| Code location | `panel/` → build output copied to `server/src/mockan/admin/static/` (`npm run build:server`) |
| UI kit | shadcn/ui (Radix) + Tailwind CSS v4, re-themed with tokens in `panel/src/styles/globals.css` |
| Server state | TanStack Query; forms with react-hook-form + zod |
| Bundle | Initial JS ≈ 184 KB gzip (budget 250 KB); Monaco and every screen are lazy-loaded |
| API | Admin API at `/api/v1` (arch §10), cookie session; dev uses MSW handlers in `panel/src/mocks/` |
| Phase | **Phase 1 (M0–M4) complete**, awaiting review. Phase 2 (M5) not started. |

## Quick start

```bash
cd panel
npm ci
npm run dev              # http://localhost:5173 with the MSW mock backend
npm run check            # typecheck + lint + unit/component tests + build
npm run e2e              # Playwright PRD §6 journey (needs a Chromium, see testing.md)
```

Open `http://localhost:5173/__design` (dev only) for the living style guide. Append `?mswScenario=new` to any URL to start as a brand-new Developer (see [testing.md](testing.md#msw-scenarios)).

## Configuration (build-time env)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_PANEL_BASE_PATH` | `/` | Vite `base` and router basename. `TODO(OQ-03)` |
| `VITE_MOCKAN_PUBLIC_BASE_URL` | `https://mock.novin-tools.com` | Shown in the base URL / `.env` snippet. `TODO(OQ-F4)` |
| `VITE_USE_MSW` | dev: on · build: off | `false` in dev → real Admin API; `true` in a build → bundle MSW (demo / e2e). |

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

## Open questions

IDs are stable and never renumbered. Defaults are implemented with a `TODO(OQ-xx)` marker at the exact spot.

| ID | Question | Default implemented | Marker locations |
| --- | --- | --- | --- |
| OQ-03 | Panel at `/_mockan/admin` or a separate host? | Vite `base` + router basename from `VITE_PANEL_BASE_PATH`, default `/`. | `vite.config.ts`, `src/app/router.tsx`, `src/lib/config.ts` |
| OQ-P1 | Which phase ships scenario-switching UI? | Phase 2 (M5). Phase 1 edits the active MockResponse only; the response sub-form is keyed by response id. | `src/features/rules/response-form.tsx`, `src/api/queries/rules.ts` |
| OQ-F1 | What shape do Admin API validation errors take? | Both problem+json `errors: {field: [msg]}` and FastAPI `422 detail: [{loc, msg}]` (snake_case `loc` → camelCase field). | `src/api/client.ts`, `src/api/types.ts` |
| OQ-F2 | Dark theme? | Light only in v1; every colour is a token so a `.dark` block can be added. | `src/styles/globals.css`, `src/components/ui/sonner.tsx` |
| OQ-F3 | Is white-on-coral (3.28:1) acceptable for primary buttons? | Keep brand coral; switch the fill to `primary-active` (5.06:1) if rejected. | `src/styles/globals.css`, `src/components/ui/button.tsx` |
| OQ-F4 | Where does the Panel get `MOCKAN_PUBLIC_BASE_URL`? `GET /me` doesn't return it. | Build-time `VITE_MOCKAN_PUBLIC_BASE_URL`. Proposal: add `publicBaseUrl` to `GET /me`. | `src/lib/config.ts` |
| OQ-F5 | Admin API payload shapes (arch §10 lists routes, not bodies). | See the table below. Proposal: confirm or replace when the Admin API's OpenAPI exists. | `src/api/types.ts`, `src/api/queries/*.ts`, `src/mocks/handlers/*.ts` |

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
