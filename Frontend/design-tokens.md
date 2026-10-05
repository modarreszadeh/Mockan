---
title: Mockan Panel — Design tokens
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - ../Product/Design/shadcn-design.md
  - ../Agent/prompts/panel-dashboard.md
  - components.md
---

# Mockan Panel — Design tokens

> **Summary:** the colour, type, radius and elevation tokens the Panel uses, how they map onto shadcn's semantic tokens, measured contrast, and where the Panel deliberately deviates from the (marketing-site) design file. Source of truth for values: `panel/src/styles/globals.css`. The live rendering is at `/__design` (dev only).

**Rules**
- MUST NOT write raw colour values in components. ESLint (`no-restricted-syntax`) rejects `#rrggbb` literals outside `globals.css` and `src/mocks`.
- MUST use the design-file token names (`surface-card`, `primary-active`, …) as Tailwind colours: `bg-surface-card`, `text-primary-active`.
- Light theme only in v1 (`TODO(OQ-F2)`).

## 1. Colour tokens

| Token (CSS var) | Tailwind | Value | Role in the Panel |
| --- | --- | --- | --- |
| `--background` | `bg-background`, `bg-canvas` | `#faf9f5` | Page floor, cards, tables, inputs. No `#fff` surfaces. |
| `--foreground` | `text-foreground`, `text-ink` | `#141413` | Headings, primary text. |
| `--primary` | `bg-primary` | `#cc785c` | Coral: **one** primary button per view, active-nav marker, focus ring. Never text. |
| `--primary-active` | `bg-/text-primary-active` | `#a9583e` | Pressed primary; coral **text** (links, template params). |
| `--primary-disabled` | `bg-primary-disabled` | `#e6dfd8` | Disabled primary fill. |
| `--body` | `text-body` | `#3d3d3a` | Secondary text on `surface-card`; descriptions. |
| `--body-strong` | `text-body-strong` | `#252523` | Lead text. |
| `--muted-foreground` | `text-muted-foreground` | `#6c6a64` | Secondary text on canvas / surface-soft only. |
| `--muted-soft` | `text-muted-soft` | `#8e8b82` | Placeholders, decorative captions, switch-off track. Never information. |
| `--border`, `--input` | `border`, `border-hairline` | `#e6dfd8` | 1 px hairlines. |
| `--hairline-soft` | `border-hairline-soft` | `#ebe6df` | Dividers inside a band. |
| `--sidebar`, `--surface-soft` | `bg-sidebar`, `bg-surface-soft` | `#f5f0e8` | Sidebar; hover on table rows. |
| `--secondary`, `--muted`, `--accent`, `--surface-card` | `bg-surface-card` | `#efe9de` | Stat tiles, empty states, checklist, active nav/tab, pills. |
| `--surface-cream-strong` | `bg-surface-cream-strong` | `#e8e0d2` | Pressed secondary button. |
| `--surface-dark` | `bg-surface-dark` | `#181715` | Code and machine output only: BaseUrlCard, JSON editor frame. |
| `--surface-dark-elevated` | `bg-surface-dark-elevated` | `#252320` | Editor toolbar, buttons on dark. |
| `--surface-dark-soft` | `bg-surface-dark-soft` | `#1f1e1b` | Code areas inside dark cards, CodeBlock. |
| `--on-dark`, `--on-dark-soft` | `text-on-dark`, `text-on-dark-soft` | `#faf9f5`, `#a09d96` | Text on dark surfaces. |
| `--accent-teal` | `bg-accent-teal` | `#5db8a6` | "Proxied" dot. Never text. |
| `--accent-amber` | `bg-accent-amber` | `#e8a55a` | "Mocked" dot; non-default environment dot. Never text. |
| `--success`, `--warning`, `--error` / `--destructive` | `bg-success`, `bg-warning`, `text-error` | `#5db872`, `#d4a017`, `#c64545` | Status dots; error text on canvas. |
| `--ring` | `ring-ring` | `#cc785c` | Focus: 1 px coral border + 3 px coral ring at 30 % alpha. |
| `--elevation` | `shadow-md/lg/xl` | `0 1px 3px rgb(20 20 19 / .08)` | Popovers, dropdowns, dialogs only. `shadow-sm/xs` = none. |

## 2. Typography

Utilities are named `type-*` (defined with `@utility` in `globals.css`) so they never collide with Tailwind colour classes in `cn()` merging.

| Utility | Spec | Font | Use |
| --- | --- | --- | --- |
| `type-display-md` | 36/1.15, 600, −0.02em | Inter | Overview greeting only. |
| `type-display-sm` | 28/1.2, 600, −0.02em | Inter | One `<h1>` per page (PageHeader). |
| `type-title-md` | 18/1.4, 600 | Inter | Card, dialog, sheet titles. |
| `type-title-sm` | 16/1.4, 600 | Inter | Form section headings. |
| `type-body` | 14/1.55, 400 | Inter | Default UI text (set on `body`). |
| `type-caption` | 13/1.4, 500 | Inter | Labels, badges, table headers. |
| `type-overline` | 12/1.4, 500, +1.5px, uppercase | Inter | Sidebar group labels, "Your base URL". |
| `type-code` / `type-code-sm` | 14/1.6 / 13/1.5 | JetBrains Mono | Paths, patterns, URLs, slugs, header names, JSON. Always mono. |

Headings and titles (`type-display-*`, `type-title-*`, the wordmark and the collapsed-sidebar "M") are Inter SemiBold (600), replacing the earlier Cormorant Garamond serif. Labels, badges and overlines never exceed 500.

## 3. Radius

shadcn classes keep their meaning; the scale is defined explicitly instead of changing `--radius`:

| Class | Value | Used by |
| --- | --- | --- |
| `rounded-sm` | 4 px | Checkbox |
| `rounded-md` | 6 px | Dropdown items |
| `rounded-lg` (`--radius`) | 8 px | Buttons, inputs, selects, tabs, nav items |
| `rounded-xl` | 12 px | Cards, tables, dialogs, alerts, empty states, CodeBlock, JSON editor |
| `rounded-2xl` | 16 px | BaseUrlCard |
| `rounded-full` (`rounded-4xl` aliases it) | pill | Badges, switch |

## 4. Contrast (WCAG 2.2 AA, measured from token values)

| Pair | Ratio | Rule applied |
| --- | --- | --- |
| `primary` text on canvas | 3.11 | **Fail** → coral text uses `primary-active` (4.80). |
| White on `primary` button | 3.28 | Below 4.5. Kept per design file; `TODO(OQ-F3)`: switch to `primary-active` (5.06). |
| `muted` on canvas / surface-soft | 5.13 / 4.77 | OK. |
| `muted` on `surface-card` | 4.48 | **Fail** → use `body` (9.02) on surface-card (tabs, empty states, ANY pill moved to canvas). |
| `error` on canvas | 4.59 | OK. |
| `error` on `surface-card` | 4.01 | **Fail** → `DELETE` method pill uses canvas fill + hairline. |
| `muted-soft` on canvas | 3.23 | Placeholders only; also the switch-off track (≥ 3:1 non-text contrast). |
| `accent-teal` / `accent-amber` as text | 2.25 / 2.00 | **Never text.** Dots with ink text (7.79 / 8.74). |
| `on-dark` / `on-dark-soft` on `surface-dark` | 17.00 / 6.62 | OK. |
| `on-dark-soft` on `surface-dark-elevated` | 5.79 | OK (editor toolbar). |

Also: visible coral focus ring on every interactive element; targets ≥ 32 px in dense tables, ≥ 40 px elsewhere (buttons `h-10`, inputs `h-10`); icon-only buttons have `aria-label`; badges always carry text.

## 5. Status language

| Concept | Visual | Component |
| --- | --- | --- |
| Source Mocked / Proxied / Error | `surface-card` pill, `accent-amber` / `accent-teal` / `error` dot + ink text | `SourceBadge` |
| Rule enabled / disabled | shadcn `Switch` (checked = `primary`); disabled rows dimmed (`text-muted-foreground`) | Rules list |
| HTTP method | Mono 12 px uppercase pill on `surface-card`; `DELETE` error text and `ANY` muted text on a canvas pill (contrast) | `MethodBadge` |
| Match type | Outline pill | `MatchTypeBadge` |
| Status code | Mono; 2xx ink, 3xx body, 4xx `warning` dot, 5xx `error` dot | `StatusCode` |
| Environment | `dev`/`stage` pill; "· default" marker; amber dot for a non-default selection | `EnvBadge` |
| Phase 2 / Beta | `badge-coral` (overline) | `CoralBadge` |

## 6. Deviations from the design file

| Design file says | Panel does | Why |
| --- | --- | --- |
| Marketing scale: 64 px hero, 96 px section rhythm | Not used. Page padding 24–32 px; 32 px between sections. | Dashboards need density. |
| Larger display size for h1–h3 | The 36/28px display sizes only for page titles and the Overview greeting. | Density; tables/forms stay sans. |
| "Never document hover; nothing changes on hover" | Table rows and nav items get a subtle hover (`surface-soft` rows; `canvas` on the `surface-soft` sidebar). Buttons only change on press. | Pointer feedback in a data-heavy tool (prompt §4.1). |
| Coral used generously on callout bands | One coral primary button per view; no coral bands. | Coral = "the action". |
| Dark surfaces for showcase cards | Only for code/machine output (BaseUrlCard, JSON editor, previews). | "Show the product chrome" = real URLs and JSON. |
| `ANY` muted text, `DELETE` error text on `surface-card` pills (prompt §4.5) | Canvas pill with hairline border. | Both fail 4.5:1 on `surface-card` (4.48 / 4.01). |
| Copernicus / StyreneB | Inter 600 (headings) / Inter, self-hosted. | Licensed fonts; prompt §2 rule 5 (no Anthropic assets). |
