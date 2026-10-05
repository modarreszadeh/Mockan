---
title: Mockan Panel — Domain components
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - design-tokens.md
  - ../agent/prompts/panel-dashboard.md
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

Read-only code window: a `surface-dark-elevated` header with the **language at the top-left** and a **Copy** button (confirms with "Copied"), over a `surface-dark-soft` body. The body scrolls both ways and is a keyboard-focusable region. Syntax colours come from the dark tokens (`src/lib/highlight.ts`, no dependency): keys `on-dark`, strings `success`, numbers `accent-amber`, `true`/`false`/`null` and the HTTP version `primary`, punctuation `on-dark-soft`.

| Prop | Type | Notes |
| --- | --- | --- |
| `code` | `string` | |
| `label` | `string` | Accessible name of the scrollable region; also names the Copy button. |
| `language?` | `"json" \| "http" \| "env" \| "text"` | Label and colours. Default `text` (uncoloured). Headers use `http`; bodies use `detectBodyLanguage()`. |
| `className?` | `string` | Sizes the whole window, e.g. `max-h-72`. |

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

## Modal

The one overlay panel (OVL-R1…R5, [plan-responsive-overlays.md](plan-responsive-overlays.md)): a **centered modal at ≥ 768 px, a bottom sheet below**. The layout is CSS only (`md:`), so resizing never remounts it and a half-filled form keeps its values. Features import it from `@/components/mockan`; ESLint forbids `ui/sheet`, `ui/dialog` and `ui/alert-dialog` outside `ui/` and `confirm-dialog.tsx`.

| Export | Notes |
| --- | --- |
| `Modal`, `ModalTrigger`, `ModalClose` | Radix Dialog root, trigger, close. |
| `ModalContent` | `size?: "sm" \| "md" \| "lg"` (max width 384 / 576 / 672 px from 768 px; default `md`), `showCloseButton?` (default true). Renders the overlay, the grab handle (mobile) and the close button. Position, size and shape are owned by `size`; pass only content classes in `className`. |
| `ModalHeader`, `ModalBody`, `ModalFooter` | Header and footer stay put; `ModalBody` is the only scroll container. The footer stacks full-width buttons on mobile (primary on top) and right-aligns them on desktop. |
| `ModalTitle`, `ModalDescription` | Required for the accessible name and description. |

| Property | `< 768 px` (bottom sheet) | `≥ 768 px` (modal) |
| --- | --- | --- |
| Position | `inset-x-0 bottom-0`, full width | centered, `w-[calc(100%-2rem)]` up to the size's max |
| Height | up to 90 dvh | up to 85 dvh |
| Shape | `rounded-t-xl`, grab handle (decorative, no drag, OQ-F9) | `rounded-xl` |
| Motion | slides up | zooms in (none with `prefers-reduced-motion`) |
| Close | X (44 px target), Esc, tap outside, footer Cancel | X, Esc, click outside, footer Cancel |

With a `<form>` around body and footer, give the form `className="flex min-h-0 flex-1 flex-col"` so the body still scrolls and the footer stays pinned (`ServiceModal`). Used by `ServiceModal` (SCR-07, `md`), `LogDetailsModal` (SCR-09, `lg`) and `ImportRulesModal` (SCR-04, `md`). Rendered at `/__design` in all three sizes.

## ConfirmDialog

`AlertDialog` for destructive confirms, with the Modal's surface (`size="sm"`: centered ≥ 768 px, a bottom sheet below). It keeps `role="alertdialog"` and, unlike `Modal`, a tap outside does not dismiss it. Props: `open`, `onOpenChange`, `title`, `description`, `confirmLabel`, `destructive?`, `pending?`, `onConfirm`.

## Wordmark

Mockan's own text wordmark (Inter SemiBold + coral dot). No third-party brand assets (prompt §2 rule 5).

## LogoMark

Mockan's own logo mark: a dark rounded tile, an "M" drawn as an SVG path (no font) and the coral dot of the wordmark. Decorative (`aria-hidden`); the `Wordmark` next to it carries the name. Used on the login page above the `Wordmark`; `public/favicon.svg` is the same drawing with literal colours. Prop: `className` (default `size-14`).
