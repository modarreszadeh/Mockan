---
title: Mockan Panel — Domain components
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - design-tokens.md
  - ../Agent/prompts/panel-dashboard.md
---

# Mockan Panel — Domain components

> **Summary:** catalogue of the Mockan components in `panel/src/components/mockan/` (built on shadcn primitives): props, states and a usage snippet. Every component is rendered in all its states at `/__design` (dev only). Import from `@/components/mockan`.

## AppShell (`src/app/app-shell.tsx`)

shadcn `Sidebar` (`surface-soft`) + 56 px header. Lives in `app/` because it composes routes and queries.

| Area | Contents |
| --- | --- |
| Sidebar | Wordmark; Overview · Rules · Services · Settings; **Admin** group (Service catalog) only when `isAdmin`. Active item: `surface-card` fill + 2 px coral marker. Hover: `canvas`. Footer note. |
| Responsive | Expanded ≥ 1024 px, icon rail (tooltips) 768–1023 px, sheet < 768 px. The user can toggle; the choice holds until the breakpoint changes. |
| Header | Sidebar trigger · breadcrumb from route `handle.crumb` (last crumb only on mobile) · workspace slug pill (mono, ≥ 768 px) · `MockKillSwitch` · user menu (Settings, Sign out → `POST /auth/logout`). |
| A11y | "Skip to content" link → `#main`; `SidebarInset` is the only `<main>`. |

## MockKillSwitch

Header "Mocks on / off" switch with the enabled count (`3/6`). Turning off calls `POST /me/rules/toggle-all` with `{ isEnabled: false }`; when more than one rule is enabled it first confirms ("Turn off all n mocks?"). Turning on enables every rule. Optimistic with rollback (shared `useToggleAllRules`).

States: loading (skeleton) · no rules ("No mocks", disabled) · on · off · confirming.

## PageHeader

Display `<h1>` (`type-display-sm`), a one-line description in `body`, right-aligned actions.

| Prop | Type | Notes |
| --- | --- | --- |
| `title` | `ReactNode` | One per page. |
| `description?` | `ReactNode` | One sentence. |
| `actions?` | `ReactNode` | At most one coral primary button. |

```tsx
<PageHeader title="Mock rules" description="Sorted by match precedence." actions={<Button>New rule</Button>} />
```

## BaseUrlCard

`code-window-card` on `surface-dark`, 16 px radius. Shows `VITE_API_BASE_URL=<publicBaseUrl>/<slug>` in mono with a copy button (`onDark` button) and a "Copied" confirmation (also announced via `aria-live`). The snippet scrolls horizontally and never wraps.

| Prop | Type | Notes |
| --- | --- | --- |
| `slug` | `string` | DeveloperSlug. The base URL is `publicBaseUrl` from `GET /me` (via `usePublicBaseUrl()`), falling back to `VITE_MOCKAN_PUBLIC_BASE_URL` until it has loaded (OQ-F4). Needs a `QueryClientProvider`. |
| `hint?` | `string` | Line under the snippet. |

States: default · copied (2 s).

```tsx
<BaseUrlCard slug={developer.slug} />
```

## CodeBlock

Read-only mono block on `surface-dark-soft`; horizontal scroll, keyboard-focusable region.

| Prop | Type |
| --- | --- |
| `code` | `string` |
| `label` | `string` (accessible name) |

## JsonEditor

Monaco (lazy-loaded, bundled locally, dark theme built from tokens at runtime). Validates JSON on change and shows `Line X, Col Y: message` under the editor (PR-06). Toolbar: size counter `n / 1 MB`, **Format** (disabled while invalid).

| Prop | Type | Notes |
| --- | --- | --- |
| `id`, `label` | `string` | `label` is the editor's accessible name. |
| `value`, `onChange`, `onBlur?` | | Controlled. |
| `error?` | `string` | Form/server error; replaces the live check message. |
| `height?` | `number` | Default 280. |

States: loading (dark skeleton) · valid · invalid (error ring + message) · over 1 MB (counter highlighted; form blocks save). In Vitest the Monaco surface is replaced by a textarea (`src/test/setup.ts`).

## KeyValueEditor

Rows of key / operator / value for headers, query conditions and header conditions. Operator `equals` or `exists` (value hidden for `exists`) when `allowExists`.

| Prop | Type | Notes |
| --- | --- | --- |
| `rows`, `onChange` | `KeyValueRow[]` | `{ key, operator, value }`. Use `recordToRows` / `rowsToRecord` for header objects. |
| `keyLabel`, `valueLabel?`, `addLabel` | `string` | Inputs are labelled `"<keyLabel> <n>"`. |
| `allowExists?` | `boolean` | Conditions only. |
| `errors?` | `({ key?, value? } \| undefined)[]` | Per-row messages. |

## Badges — MethodBadge, MatchTypeBadge, SourceBadge, StatusCode, EnvBadge, CoralBadge

See [design-tokens.md §5](design-tokens.md#5-status-language). All carry text; dots are `aria-hidden`. `MethodBadge` takes any verb string (a logged request can use one the editor doesn't offer).

```tsx
<MethodBadge method="GET" /> <MatchTypeBadge matchType="Template" /> <SourceBadge source="Mocked" />
<StatusCode code={404} /> <EnvBadge environment="dev" isOverride />
```

## PatternText

Mono pattern; for `Template` patterns `{param}` / `{*rest}` are highlighted in `primary-active`. `truncate` adds an ellipsis with the full pattern in `title`.

## EmptyState

`feature-card` recipe: `surface-card`, 12 px radius, 32 px padding; lucide icon, `type-title-md` title, one sentence in `body`, one primary action.

## ProblemAlert

Renders an `ApiError`'s RFC 7807 problem: `title`, `detail`, `code` in mono, optional **Try again** (`onRetry`).

## ConfirmDialog

`AlertDialog` for destructive confirms. Props: `open`, `onOpenChange`, `title`, `description`, `confirmLabel`, `destructive?`, `pending?`, `onConfirm`.

## Wordmark

Mockan's own text wordmark (Inter SemiBold + coral dot). No third-party brand assets (prompt §2 rule 5).

## LogoMark

Mockan's own logo mark: a dark rounded tile, an "M" drawn as an SVG path (no font) and the coral dot of the wordmark. Decorative (`aria-hidden`); the `Wordmark` next to it carries the name. Used on the login page above the `Wordmark`; `public/favicon.svg` is the same drawing with literal colours. Prop: `className` (default `size-14`).
