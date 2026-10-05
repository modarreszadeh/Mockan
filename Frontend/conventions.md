---
title: Mockan Panel — Conventions
status: Draft (v0.1)
date: 2026-10-03
owner: Frontend team
related:
  - project-structure.md
  - ../Agent/mockan-architecture.md
---

# Mockan Panel — Conventions

> **Summary:** rules Panel code follows. ESLint enforces import boundaries and "no raw hex"; reviewers enforce the rest. Architecture §14 and the prompt's hard rules always win.

## 1. Naming

| Thing | Style | Example |
| --- | --- | --- |
| Glossary concepts (arch §2) | exact glossary word in types, UI copy and file names | `Developer`, `DeveloperSlug`, `Service`, `ServiceEnvironment`, `MockRule`, `MockResponse`, `Upstream` |
| `MockResponse` in UI copy | "Scenario" | "Active scenario" |
| Files | kebab-case | `base-url-card.tsx`, `rule-editor-page.tsx` |
| Components / types | PascalCase | `BaseUrlCard`, `MockRuleUpdate` |
| Hooks | `use` + resource + verb | `useRules`, `useToggleRule`, `useSaveRule` |
| JSON on the wire and TS fields | camelCase | `activeResponseId`, `allowedOrigins` |
| Tests that cover a requirement | start with the ID | `"PR-05 template pattern rejects {*rest} in the middle"` |

MUST NOT use `tenant`, `project`, `endpoint mock` or other non-glossary words.

## 2. Feature layout

Each folder in `src/features/<name>/` owns one screen (or a family): `<name>-page.tsx` (route component, handles loading/empty/error/success), sub-components next to it, and `<name>.test.tsx`. Every screen implements **four states**: loading (skeletons shaped like content, never spinners), empty, error (`ProblemAlert` + retry), success.

## 3. Server state

- Query keys come only from `src/api/queries/keys.ts` (`ruleKeys.list()`, `ruleKeys.detail(id)`, `serviceKeys.list()`, `serviceSettingKeys.all`, `meKeys.all`).
- Mutations invalidate exactly the affected keys.
- Toggles (rule, all rules, environment) are optimistic: snapshot → patch cache → rollback + error toast on failure → invalidate on settle.
- After a change that reaches the Gateway, show the quiet toast **"Saved — live in about 2 seconds"** (PR-07).

## 4. Errors

- `apiRequest` throws `ApiError` with the parsed problem+json (`title`, `detail`, `code`) and `fieldErrors` (camelCase dot paths, both shapes — OQ-F1).
- `401` anywhere → full-page navigation to `/api/v1/auth/login`.
- Forms map `fieldErrors` onto fields with `setError`; only errors with no matching field go to a `ProblemAlert` above the form. Never only a toast.
- Screens render `ProblemAlert` with a retry for failed queries.
- Never log request/response headers or bodies to the console (NFR-07).

## 5. Styling

- Tokens only (design-tokens.md). Type via `type-*` utilities; paths, patterns, URLs, slugs and header names always `font-mono`.
- One coral primary button per view.
- Overlay panels are `Modal` or `ConfirmDialog` from `@/components/mockan`, never `ui/sheet`, `ui/dialog` or `ui/alert-dialog` directly (ESLint). They are modals from 768 px and bottom sheets below; features do not choose a side, a width or a breakpoint ([plan-responsive-overlays.md](plan-responsive-overlays.md)).
- Icons: lucide, 16 px in dense UI, 20 px in headers, `strokeWidth={1.75}`, `aria-hidden` when decorative; icon-only buttons need `aria-label`.
- `components/ui/` files are shadcn-generated: only token-level edits (radius, ring alpha, heights, hover/press per design-tokens.md §6).

## 6. Copy

- Sentence case. Short. Glossary words.
- Errors say what happened and what to do next ("Start the pattern with “/”.").
- Exact copy from the PRD where it exists, e.g. the empty state "No rules yet — all traffic is proxied. Create your first mock."

## 7. Open questions in code

Implement the stated default and leave `// TODO(OQ-xx): <one line>` at the exact spot. The list lives in [README.md](README.md#open-questions).
