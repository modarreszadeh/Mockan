---
title: Mockan Panel — Tech stack
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - README.md
  - ../Agent/prompts/panel-dashboard.md
---

# Mockan Panel — Tech stack

> **Summary:** every library the Panel uses, its pinned version (exact, in `panel/package.json`) and why. Change a version → update this table in the same PR (C-01).

## Runtime

| Concern | Library | Version | Why |
| --- | --- | --- | --- |
| UI runtime | `react`, `react-dom` | 19.3.0 | D-11. |
| Language | `typescript` | 6.0.3 | `strict` + `noUncheckedIndexedAccess`. |
| Build / dev server | `vite`, `@vitejs/plugin-react` | 8.3.2, 6.1.1 | D-11. `base` from `VITE_PANEL_BASE_PATH` (OQ-03). |
| Styling | `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | Tokens exposed via `@theme inline`. |
| Component kit | `shadcn` (CLI + `shadcn/tailwind.css`), `radix-ui` | 4.21.1, 1.6.7 | Accessible primitives; components copied into `src/components/ui/` (style `radix-nova`). |
| Class merging | `cn`, `class-variance-authority` | 0.4.0, 0.7.1 | `cn` is shadcn's clsx + tailwind-merge replacement. |
| Animations | `tw-animate-css` | 1.4.0 | shadcn enter/exit animations. |
| Icons | `lucide-react` | 1.51.0 | 16 px in dense UI, 20 px in headers, stroke 1.75. |
| Routing | `react-router` (data router) | 8.4.0 | `createBrowserRouter`, `lazy` routes, `useBlocker` for unsaved changes. |
| Server state | `@tanstack/react-query` | 5.104.1 | Caching, optimistic toggles, invalidation by key factory. |
| Forms | `react-hook-form`, `@hookform/resolvers`, `zod` | 7.89.0, 5.9.1, 4.6.5 | zod schemas mirror arch §10 validation. |
| Code editor | `@monaco-editor/react`, `monaco-editor` | 4.7.0, 0.57.0 | JSON body editor (arch §11). Bundled locally (no CDN — NFR-05) and lazy-loaded. |
| Toasts | `sonner` | 2.0.8 | shadcn's toast. |
| Command palette | `cmdk` | 1.1.1 | Status-code combobox. |
| Fonts | `@fontsource/inter`, `@fontsource/jetbrains-mono` | 5.3.0 | Self-hosted (internal network, NFR-05). Inter 600 is the heading and title weight. |

## Development and test

| Concern | Library | Version | Why |
| --- | --- | --- | --- |
| API mocking | `msw` | 2.15.0 | The Admin API doesn't exist yet. v2 kept over v3 (v3 requires `graphql` as a peer). |
| Unit / component tests | `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` | 5.0.3, 30.1.1, 16.3.3, 14.6.7, 7.0.1 | |
| Accessibility | `vitest-axe`, `axe-core` | 0.1.0, 4.13.0 | `toHaveNoViolations` on every screen (works with Vitest 5). |
| E2E | `@playwright/test` | 1.63.0 | PRD §6 journey against MSW. |
| Lint / format | `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks`, `prettier` (+ tailwind plugin) | 10.12.0, 8.71.0, 7.1.1, 3.9.9 | Lint also enforces import boundaries and "no raw hex". |
