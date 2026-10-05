---
title: Mockan Panel — Plan: modals on desktop, bottom sheets on mobile
status: Done
date: 2026-10-05
owner: Frontend team
breaking: true
related:
  - components.md
  - screens.md
  - conventions.md
  - design-tokens.md
  - project-structure.md
  - testing.md
  - ../agent/prompts/panel-dashboard.md
audience: Frontend engineers and AI coding agents working in `panel/`
---

# Plan: modals on desktop, bottom sheets on mobile

> **Summary:** every overlay panel in the Panel (side Sheet/drawer, Dialog, AlertDialog) becomes one responsive surface: a **centered modal at ≥ 768 px** and a **bottom sheet at < 768 px**. A new `Modal` component in `components/mockan/` owns the layout; `ConfirmDialog` reuses it. Right-edge Sheets disappear from features. It is a breaking change for component names, imports and UI wording; the Admin API, routes and behaviour do not change.

## 1. Goal and scope

| ID | Requirement |
| --- | --- |
| OVL-R1 | At viewport width **≥ 768 px** (Tailwind `md`, the same as `MOBILE_BREAKPOINT` in `src/hooks/use-mobile.ts`) every overlay panel is a centered modal with a dimmed backdrop. |
| OVL-R2 | At **< 768 px** the same overlay is a bottom sheet: full width, anchored to the bottom edge, rounded top corners, slides up, at most 90 % of the dynamic viewport height, body scrolls inside. |
| OVL-R3 | One implementation decides the layout. Features never pick a side, a width breakpoint or an animation themselves. |
| OVL-R4 | Accessibility does not regress: `role="dialog"` / `role="alertdialog"`, labelled by the title, focus trap, focus returns to the trigger, Esc closes, axe passes. |
| OVL-R5 | Resizing across 768 px while an overlay is open keeps it open and keeps form state (no remount). |

### In scope (the full inventory, found by searching `src/` for `ui/sheet`, `ui/dialog`, `ui/alert-dialog`)

| # | Component | File | Screen | Today | Desktop target | Mobile target |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `LogDetailsSheet` | `src/features/logs/log-details-sheet.tsx` | SCR-09 | Right `Sheet`, full height, `sm:max-w-2xl` | `Modal size="lg"` | Bottom sheet |
| 2 | `ServiceSheet` | `src/features/admin/service-sheet.tsx` | SCR-07 | Right `Sheet`, full height, `sm:max-w-xl`, contains a `<form>` | `Modal size="md"` | Bottom sheet |
| 3 | `ImportRulesDialog` | `src/features/rules/rules-transfer-ui.tsx` | SCR-04 | Centered `Dialog`, `sm:max-w-xl` | `Modal size="md"` | Bottom sheet |
| 4 | `ConfirmDialog` | `src/components/mockan/confirm-dialog.tsx` | many | Centered `AlertDialog`, `max-w-sm` | Centered alert modal (`size="sm"`), unchanged look | Bottom sheet, still `alertdialog` |

`ConfirmDialog` call sites (no code change needed, they get the new layout for free): `mock-kill-switch.tsx`, `rules-page.tsx` (delete rule, disable all), `rule-editor-page.tsx` (4), `service-catalog-page.tsx`, `settings-page.tsx`, `onboarding-page.tsx`, `design-page.tsx`.

### Out of scope

| Item | Why | Tracked as |
| --- | --- | --- |
| Mobile sidebar (`Sheet side="left"` inside `src/components/ui/sidebar.tsx`) | Navigation drawer, not a content panel; a left drawer is the expected pattern for app navigation. | OQ-F7 |
| `Select`, `DropdownMenu`, `Popover`, `Tooltip`, `Command` | Anchored menus, not panels. | OQ-F8 |
| Toasts (`sonner`) | Not overlays that block the page. | — |
| Drag-to-dismiss on the bottom sheet | Needs a gesture library; see D-OVL3. | OQ-F9 |

## 2. Decisions

| ID | Decision | Rationale | Rejected alternative |
| --- | --- | --- | --- |
| D-OVL1 | **CSS-only responsive layout** with Tailwind `md:` variants on a single Radix `Dialog.Content`. | One DOM tree, so no remount on resize (OVL-R5), no JS breakpoint, no hydration of a media query, and unit tests in jsdom see the same `role="dialog"` as today. `md` = 768 px matches `useIsMobile()`, the sidebar and the table→card switch. | Swap `Dialog` ↔ `Drawer` with `useIsMobile()` (the shadcn "responsive dialog" recipe): remounts on resize and loses `ServiceForm` state, two components to keep in sync. |
| D-OVL2 | The new component lives in **`src/components/mockan/modal.tsx`**, built from `radix-ui` `Dialog` primitives and `ui/button`. `components/ui/*` stays untouched. | `conventions.md` §5 and `project-structure.md` allow only token-level edits in `components/ui/`. A layout change is not token-level. | Edit `ui/dialog.tsx` and `ui/sheet.tsx` in place: breaks the shadcn-regeneration rule. |
| D-OVL3 | **No new dependency** (no `vaul`). Bottom sheet closes by the X button, Esc, a backdrop tap or a Cancel button; the grab handle is decorative. | Keeps the bundle budget and the dependency list unchanged; Radix Dialog already gives focus trap, scroll lock and portals. | `vaul` for drag-to-dismiss: new dependency, and it would need the D-OVL1 swap anyway. Revisit under OQ-F9. |
| D-OVL4 | `ConfirmDialog` keeps the `AlertDialog` primitive (role `alertdialog`, no dismiss on backdrop tap) and reuses the **same surface classes** exported from `modal.tsx`. | Destructive confirms must stay deliberate; only the layout is shared. | Build `ConfirmDialog` on `Modal`: would lose `alertdialog` semantics. |
| D-OVL5 | Vocabulary: **"modal"** for the component and in docs; "bottom sheet" only when describing the mobile layout. "Drawer" and "Sheet" are retired for content panels. | One word per concept (glossary discipline, `CONTEXT.md`). | Keep "drawer" in SCR-09 copy and docs. |

## 3. Design spec

### 3.1 `Modal` API (`src/components/mockan/modal.tsx`, re-exported from `@/components/mockan`)

| Export | Built on | Notes |
| --- | --- | --- |
| `Modal` | `Dialog.Root` | `open`, `onOpenChange`, `defaultOpen`. |
| `ModalTrigger`, `ModalClose` | `Dialog.Trigger`, `Dialog.Close` | `asChild` supported. |
| `ModalContent` | `Dialog.Portal` + `Dialog.Overlay` + `Dialog.Content` | Props: `size?: "sm" \| "md" \| "lg"` (default `"md"`), `showCloseButton?: boolean` (default `true`), plus Radix content props. Renders the grab handle and the close button. |
| `ModalHeader` | `div` | `shrink-0`, padding `p-6` (mobile `px-4 pt-2 pb-4`). |
| `ModalBody` | `div` | `min-h-0 flex-1 overflow-y-auto overscroll-contain`; the only scroll container. |
| `ModalFooter` | `div` | `shrink-0 border-t`; buttons stack full width on mobile (`flex-col-reverse`), row and right-aligned on desktop. |
| `ModalTitle`, `ModalDescription` | `Dialog.Title`, `Dialog.Description` | `type-title-md` / `text-body`. A title is required (Radix warns otherwise). |
| `modalSurfaceClass(size)` | — | The class string used by `ModalContent`, exported for `ConfirmDialog` (D-OVL4). |

Usage (what every feature writes):

```tsx
<Modal open={open} onOpenChange={onOpenChange}>
  <ModalContent size="lg">
    <ModalHeader>
      <ModalTitle>…</ModalTitle>
      <ModalDescription>…</ModalDescription>
    </ModalHeader>
    <ModalBody>…</ModalBody>
    <ModalFooter>…</ModalFooter>
  </ModalContent>
</Modal>
```

When a `<form>` wraps body and footer (`ServiceModal`), the form gets `className="flex min-h-0 flex-1 flex-col"` so `ModalBody` still scrolls and the footer stays pinned.

### 3.2 Layout per breakpoint

| Property | Mobile `< 768 px` (base classes) | Desktop `≥ 768 px` (`md:` classes) |
| --- | --- | --- |
| Position | `fixed inset-x-0 bottom-0` | `fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2` (reset `bottom`/`inset-x`) |
| Width | `w-full` | `w-[calc(100%-2rem)]`, max: `sm` = `max-w-sm` (384 px), `md` = `max-w-xl` (576 px), `lg` = `max-w-2xl` (672 px) |
| Height | `max-h-[90dvh]`, content-sized | `max-h-[85dvh]`, content-sized |
| Shape | `rounded-t-xl` (12 px, design-tokens §3), `border-t` hairline | `rounded-xl`, `ring-1 ring-border` |
| Safe area | `pb-[env(safe-area-inset-bottom)]` | — |
| Grab handle | 40 × 4 px pill, hairline token, `aria-hidden`, `md:hidden` | hidden |
| Enter / exit | fade + `slide-in-from-bottom` / `slide-out-to-bottom` | fade + `zoom-in-95` / `zoom-out-95` (as today) |
| Reduced motion | `motion-reduce:animate-none` | same |
| Backdrop | existing overlay (`bg-black/10` + blur) | same |
| Elevation | `--elevation` (design-tokens §1: dialogs only) | same |
| Structure | `flex flex-col`: header · body (scrolls) · footer (pinned) | same |

### 3.3 Behaviour

- Close: X button (top right, 44 × 44 px touch target on mobile), Esc, backdrop tap (`Modal` only; `ConfirmDialog` ignores backdrop taps), footer Cancel.
- Focus: Radix default (first focusable, trapped, returns to trigger). `LogDetailsModal` keeps focus on the content, not on "Mock this", via `onOpenAutoFocus` so a stray Enter cannot create a rule.
- Scroll: Radix locks page scroll; only `ModalBody` scrolls. Code blocks inside keep horizontal scroll, never wrap.
- Nested portals (`Select` inside `ServiceModal`): both use `z-50`; the later portal paints on top. Verify on mobile (task OVL-T3).
- Virtual keyboard: add `interactive-widget=resizes-content` to the viewport meta in `panel/index.html` so Chrome on Android shrinks `dvh` when the keyboard opens. iOS Safari ignores it; check manually that a focused field near the bottom of `ServiceModal` scrolls into view.

## 4. Breaking changes

| Area | Before | After | Who is affected |
| --- | --- | --- | --- |
| Component names / files | `LogDetailsSheet` (`log-details-sheet.tsx`), `ServiceSheet` (`service-sheet.tsx`), `ImportRulesDialog` | `LogDetailsModal` (`log-details-modal.tsx`), `ServiceModal` (`service-modal.tsx`), `ImportRulesModal` | Importers in `logs-page.tsx`, `service-catalog-page.tsx`, `rules-page.tsx`. `ConfirmDialog` keeps its name and props. |
| Imports | Features import `@/components/ui/sheet`, `ui/dialog`, `ui/alert-dialog` directly | Forbidden by ESLint; use `Modal` / `ConfirmDialog` from `@/components/mockan`. `ui/sheet` is only used by `ui/sidebar.tsx`. | All feature code and future agents. |
| Desktop UX | Log details and Service form slide in from the right, full height | Centered modal, content height up to 85 dvh | Admins (SCR-07), Developers using the live log (SCR-09). |
| Mobile UX | Right sheet at 75 % width; dialogs as a small centered card | Full-width bottom sheet | All mobile users. |
| Wording | "drawer", "right Sheet" in docs and test names | "modal" (D-OVL5) | Docs, test titles, e2e variable names. |
| Not changed | — | Admin API, routes, query keys, copy inside the panels, `role` values, accessible names | Unit tests that query `getByRole("dialog" \| "alertdialog", { name })` keep passing. |

## 5. Tasks

Each task is one commit on its own, keeps `npm run check` green, and can be reverted alone. Do them in order.

| ID | Task | Files | Done when |
| --- | --- | --- | --- |
| OVL-T1 | Build `Modal` (§3.1–3.3) and export it. Rebuild `ConfirmDialog` on `AlertDialog` primitives + `modalSurfaceClass("sm")`. Add Modal sm/md/lg (with a long scrolling body and a form) to `/__design`. | `src/components/mockan/modal.tsx` (new), `confirm-dialog.tsx`, `index.ts`, `src/features/design/design-page.tsx`, `src/components/mockan/components.test.tsx` | Unit tests: role `dialog`, labelled by title, X and Esc close, focus returns to trigger, axe clean; `ConfirmDialog` still `alertdialog` and ignores backdrop clicks. |
| OVL-T2 | Migrate the import dialog → `ImportRulesModal` (`size="md"`). | `src/features/rules/rules-transfer-ui.tsx`, `rules-page.tsx` | `transfer.test.tsx` passes unchanged apart from the renamed import. |
| OVL-T3 | Migrate `ServiceSheet` → `ServiceModal` (`size="md"`), form wraps body + footer (§3.1). Rename file. Update the file's doc comment ("right Sheet" → "modal"). | `src/features/admin/service-modal.tsx` (renamed), `service-catalog-page.tsx` | `service-catalog.test.tsx` passes; at 390 px the environment `Select` opens above the sheet and the footer stays visible while the body scrolls. |
| OVL-T4 | Migrate `LogDetailsSheet` → `LogDetailsModal` (`size="lg"`), `onOpenAutoFocus` per §3.3. Rename file; doc comment "Details drawer" → "Details modal". | `src/features/logs/log-details-modal.tsx` (renamed), `logs-page.tsx` | `logs.test.tsx` passes; test titles say "details modal". |
| OVL-T5 | ESLint guard: in `src/features/**` and `src/components/mockan/**` forbid `@/components/ui/sheet`, `@/components/ui/dialog`, `@/components/ui/alert-dialog` with the message "Use Modal or ConfirmDialog from components/mockan (plan-responsive-overlays.md)". Allow them only in `modal.tsx` and `confirm-dialog.tsx`. | `panel/eslint.config.js` | `npm run lint` fails on a scratch import of `ui/sheet` in a feature, passes on the tree. |
| OVL-T6 | Viewport meta: add `interactive-widget=resizes-content`. | `panel/index.html` | Present; no layout change at 1440 px. |
| OVL-T7 | E2E: add a `mobile` Playwright project (390 × 844, `hasTouch`, `isMobile`) next to `chromium`. New `e2e/overlays.spec.ts` opens each of the four overlays at both sizes and asserts geometry (below). Rename the `drawer` variable in `phase2.spec.ts`. | `panel/playwright.config.ts`, `panel/e2e/overlays.spec.ts` (new), `panel/e2e/phase2.spec.ts` | `npm run e2e` green on both projects. |
| OVL-T8 | Docs (§6) and screenshots: add `scr-07-service-modal-{1440,390}.png`, `scr-09-log-details-{1440,390}.png`, `confirm-dialog-390.png` to `docs/frontend/screenshots/`. | see §6 | Docs say "modal" everywhere; screenshots table updated. |

Geometry assertions for OVL-T7 (tolerance 1 px), using `locator.boundingBox()` on `getByRole("dialog" | "alertdialog")` after the enter animation:

| Project | Assertion |
| --- | --- |
| `mobile` (390 × 844) | `x == 0`, `width == 390`, `y + height == 844`, `height ≤ 0.9 × 844`; `document.documentElement.scrollWidth == 390` (no horizontal page scroll). |
| `chromium` (1440 × 900) | `x + width/2 == 720`, `y + height/2 == 450`, `width ≤` the size's max (384 / 576 / 672), `height ≤ 0.85 × 900`. |

## 6. Documentation changes (C-01)

| File | Change |
| --- | --- |
| `docs/frontend/components.md` | New section **Modal**: purpose, API table (§3.1), layout table (§3.2), usage snippet, states (closed · open · scrolling · pending). **ConfirmDialog**: "built on `AlertDialog` with the Modal surface; bottom sheet < 768 px". |
| `docs/frontend/screens.md` | SCR-04: "Import" opens a modal. SCR-07: "create/edit in a right `Sheet`" → "in a modal (bottom sheet on mobile)"; "the sheet keeps the new Service" → "the modal keeps…". SCR-09: "Details drawer" → "Details modal"; "the drawer's one primary button" → "the modal's…"; checklist item wording. Screenshots table: new rows from OVL-T8. |
| `docs/frontend/conventions.md` | §5 Styling: "Overlay panels use `Modal` or `ConfirmDialog` from `@/components/mockan`, never `ui/sheet` / `ui/dialog` / `ui/alert-dialog` directly (ESLint). They are modals ≥ 768 px and bottom sheets < 768 px; features do not choose a side or width breakpoint." |
| `docs/frontend/design-tokens.md` | §3 Radius: dialogs `rounded-xl`; bottom sheets `rounded-t-xl`. §2: `type-title-md` "Card and modal titles". |
| `docs/frontend/project-structure.md` | Import-rules table: add the `ui/sheet|dialog|alert-dialog` restriction. |
| `docs/frontend/testing.md` | E2E: the `mobile` project and `overlays.spec.ts`. |
| `docs/frontend/README.md` | Documents table: add this plan; Open questions: add OQ-F7, OQ-F8, OQ-F9 (§8). When done, set this plan's `status: Done`. |
| `docs/agent/prompts/panel-dashboard.md` | Do not rewrite the brief. Next to the SCR-07 "right `Sheet`" line and the M5 "details drawer" line, add a note that they are superseded by this plan, in the same style as the typography note (commit `96e5cd7`). |
| `docs/product/mockan-prd.md` | §SCR-09 checklist: "a details drawer shows" → "a details view shows" (product docs stay layout-neutral). |

## 7. Acceptance checklist

- [x] At 1440 px, the log details, Service form, import and every confirm open as centered modals with a backdrop; none touches a viewport edge.
- [x] At 390 px and 360 px, the same overlays open as full-width bottom sheets with rounded top corners and a grab handle; no horizontal page scroll.
- [x] Long content scrolls inside the body; header and footer stay visible. *(Not checked on a real iPhone: the footer clearing the home indicator uses `env(safe-area-inset-bottom)`.)*
- [x] Resizing from 1440 px to 390 px with the Service form open and half filled keeps it open and keeps the typed values.
- [x] Esc, the X button and Cancel close every overlay; a backdrop tap closes `Modal` but not `ConfirmDialog`.
- [x] Focus is trapped and returns to the trigger; axe passes for each overlay in unit tests.
- [x] `prefers-reduced-motion: reduce` shows no slide or zoom. *(`motion-reduce:animate-none` is set; not exercised in a browser.)*
- [x] `grep -rn "ui/sheet\|ui/dialog\|ui/alert-dialog" panel/src/features` finds nothing; ESLint enforces it.
- [x] `npm run check` and `npm run e2e` (both projects) are green; initial JS stays under the 250 KB gzip budget (≈ 187 KB).
- [x] Docs in §6 updated; no "drawer" or "right Sheet" left in `docs/frontend/` for content panels.

## 8. Open questions

IDs continue the Frontend list in [README.md](README.md#open-questions). Defaults are what this plan implements.

| ID | Question | Default |
| --- | --- | --- |
| OQ-F7 | Should the mobile sidebar (left `Sheet` < 768 px) also become a bottom sheet? | No: it is navigation, it stays a left drawer. |
| OQ-F8 | Should `Select` / `DropdownMenu` open as bottom sheets on mobile? | No: they stay anchored popovers. |
| OQ-F9 | Is drag-to-dismiss on the bottom sheet required? | No: X, Esc, backdrop and Cancel only (D-OVL3). If required, evaluate a gesture library against the bundle budget and its maintenance status first. |

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| iOS Safari: the virtual keyboard covers the lower fields of `ServiceModal` (`dvh` ignores the keyboard there). | Body is the scroll container, so the browser can scroll a focused field into view; check manually on an iPhone (OVL-T3). |
| Desktop log details lose the full-height reading space of the right sheet. | `size="lg"` (672 px) and `max-h-[85dvh]`; code blocks keep `max-h-72` with their own scroll. |
| Agents re-introduce `Sheet` from shadcn examples. | ESLint guard (OVL-T5) with a message that points here; conventions.md §5. |
| `tailwind-merge` (`cn`) drops a responsive class when a caller passes `className` to `ModalContent`. | Callers pass only content classes (padding, gap); position, size and shape are owned by `size`. Covered by the geometry e2e. |
