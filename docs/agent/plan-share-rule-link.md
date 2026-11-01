---
title: Plan — Share a MockRule by public link
status: Approved for implementation
date: 2026-11-01
audience: Engineers and AI coding agents
---

# Plan — Share a MockRule by public link

## Why

A frontend Developer creates a MockRule for an endpoint that doesn't exist yet and wants the backend
teammate to review the contract (path, method, conditions, status, headers, body) together. Today the
backend teammate can only see it by signing in as that Developer or reading an export file.

## What the user gets

1. Rules list (SCR-04) row menu `⋯` gets a **Share** item (between *Copy as curl* and the separator before
   *Delete*). Selecting it creates (or reuses) the rule's public link, copies it to the clipboard and
   toasts: "Public link copied — anyone with the link can view this rule".
2. Once a rule is shared, the row shows a small **Shared** badge next to the rule name, and the menu shows
   **Copy share link** (instead of *Share*) and **Stop sharing**. Stop sharing revokes the link (old URL
   → "link not available" page); sharing again creates a **new** token.
3. The link opens a **read-only, public preview page** at `{panel}/shared/{token}`. No sign-in needed.
   It shows the rule **live** (current state, so edits after review feedback are visible on refresh):
   - header: Mockan wordmark, rule name, "Shared by {owner displayName}", "Read-only preview", last updated.
   - request card: method badge, match type badge, pattern (`PatternText`), Service (name + path prefix or
     "Any"), priority, enabled/disabled, query conditions and header conditions (table or "None"),
     and the mock URL `{publicBaseUrl}/{ownerSlug}{pattern}` with a copy button for Exact rules.
   - scenarios: one tab per scenario (active one marked "Active"); each shows status code + reason
     phrase, delay, content type, body mode, response headers (key/value list) and the body in
     `CodeBlock` (pretty-printed when JSON).
   - unknown/revoked token → friendly "This link isn't available" page (no app shell).
   - mobile (390px) and desktop (1440px) layouts both work; no horizontal page scroll.

## Decisions

| # | Decision | Why |
| --- | --- | --- |
| S-1 | Token stored on the rule: `mock_rules.share_token varchar(64) NULL UNIQUE`. Token = `secrets.token_urlsafe(24)` (32 chars, 192 bits). | One link per rule, revocable, unguessable; lookup by unique index. |
| S-2 | The preview is **live**, not a frozen snapshot. | Review loop: frontend edits, backend refreshes. |
| S-3 | Public endpoint lives under the Admin API without auth: `GET /api/v1/shared/rules/{token}`. Returns `404 not_found` for unknown token, revoked token, or a **disabled owner**. Response headers: `Cache-Control: no-store`, `X-Robots-Tag: noindex`. | Admin already serves the Panel; Mockan is internal-network only (NFR-05), so "anyone with link" = anyone on the VPN with the link. |
| S-4 | The public payload is a dedicated `SharedRuleOut` — never `developerId`, `ssoSubject`, or `shareToken`. Owner exposed as `{ displayName, slug }`. Service as `{ name, pathPrefix } \| null`. Includes `publicBaseUrl` (from settings, same source as `GET /me`). | Minimum disclosure. |
| S-5 | Owner endpoints: `POST /api/v1/me/rules/{id}/share` (WritableDeveloper; idempotent — returns existing token if already shared; 200 `{ shareToken }`) and `DELETE /api/v1/me/rules/{id}/share` (204, idempotent). Both audited as `AuditAction.UPDATE` on `mock_rule` with `changes = {"shared": [old, new]}` (follow the existing `diff` shape in `services/changes.py`). | No new audit enum value → no CHECK-constraint migration. |
| S-6 | `MockRuleOut` gains `shareToken: string \| null` so the Panel knows the state. The URL is built **client-side**: `${window.location.origin}${PANEL_BASE_PATH-without-trailing-slash}/shared/${token}`. | Server doesn't need to know the Panel's public origin. |
| S-7 | Share token is **not** exported (FR-12 export), **not** copied by Duplicate, and dies with the rule on delete. Import never sets it. | Sharing is a per-rule, per-moment decision. |
| S-8 | Sharing does not change matching; the Gateway snapshot ignores the column and no NOTIFY is needed (but harmless if the existing commit path sends one). | Not a config change for traffic. |
| S-9 | The menu label is **Share** (verb, like the other items); the state badge is **Shared**. | Matches the user's "Shared" wording for the state while keeping menu verbs consistent. |

## Backend work (`server/`)

1. **Model** `infrastructure/db/models.py` → `MockRule.share_token: Mapped[str | None] = mapped_column(String(64), unique=True)` (naming convention gives `uq_mock_rules_share_token`).
2. **Migration** `migrations/versions/20261101_xxxx_rule_share_token.py`, revision `"0003"`, down_revision `"0002"`: add column + unique constraint; downgrade drops both. Follow the style of `0002`.
3. **Schemas** `admin/schemas/rule.py`: add `share_token: str | None` to `MockRuleOut`; new `ShareOut { share_token }`. New `admin/schemas/shared.py` with `SharedRuleOut` (name, method, match_type, pattern, query/header conditions, priority, is_enabled, active_response_id, responses: list[MockResponseOut], service: SharedServiceOut | None, owner: SharedOwnerOut, public_base_url, updated_at). Verify `rules_io` export models don't pick it up.
4. **Services** `admin/services/rules.py`: `share_rule(session, developer, rule_id) -> str`, `unshare_rule(...)`. New `admin/services/shared.py`: `get_shared_rule(session, token)` → joins owner Developer (404 if disabled) and Service; `selectinload` responses (relationships are `lazy="raise"`).
5. **Routers**: add the two owner routes to `admin/routers/rules.py`; new `admin/routers/shared.py` (`prefix="/shared"`, tag `shared`, **no auth dependency**) included in `admin/app.py`. Use `problems(404)` docs.
6. **Tests** (`server/tests/admin/`): `test_shared_api.py` — share returns token, idempotent, `GET /me/rules` shows it, public GET works **without a session cookie**, payload has no `developerId`/`shareToken`, unshare → public 404, re-share gives a new token, another Developer can't share/unshare your rule (404), disabled owner → 404, deleting the rule kills the link, export file has no `shareToken`. Update `openapi.snapshot.json` (see how `test_openapi.py` regenerates it). Run `server/scripts/check.sh` (needs Docker for Postgres testcontainers).

## Panel work (`panel/`)

1. **Types** `api/types.ts`: `shareToken: string | null` on `MockRule`; `SharedRule` type mirroring `SharedRuleOut`.
2. **Queries**: in `api/queries/rules.ts` add `useShareRule()` / `useUnshareRule()` (patch rule caches with the new token, like the toggle helpers). New `api/queries/shared.ts` with `useSharedRule(token)`. Add `ruleKeys`/new keys in `keys.ts`. The public page must **not** trigger `redirectToLogin()` — the endpoint never returns 401, but double-check the client path; add an option if needed.
3. **Share URL helper** `lib/share.ts`: `shareUrl(token)` (uses `PANEL_BASE_PATH`) + unit test.
4. **Rules page** `features/rules/rules-page.tsx` row actions: Share / Copy share link / Stop sharing (lucide icons `Share2`, `Link`, `Link2Off`), clipboard + toasts following the existing "Copy as curl" pattern; **Shared** badge next to the name (use existing badge components; check mobile card layout of the row too).
5. **Public page** `features/shared/shared-rule-page.tsx` + route `shared/:token` in `app/router.tsx` **outside `<AuthGate>`** (sibling of `login`). Standalone layout; reuse `MethodBadge`, `MatchTypeBadge`, `PatternText`, `StatusCode`, `CodeBlock`, `Wordmark`, `Tabs`, `Card`, `reasonPhrase`, `formatDelay`. Add `<meta name="robots" content="noindex">` via effect or document title "{rule name} · Mockan". Not-found state for 404.
6. **MSW**: `mocks/db.ts` field `shareToken`, handlers in `mocks/handlers/rules.ts` (share/unshare) and a new `mocks/handlers/shared.ts` registered in `handlers/index.ts`; the public handler must not require the mock session.
7. **Tests** (vitest + Testing Library, follow `features/rules/rules.test.tsx`): menu Share copies the URL and shows the badge; Stop sharing removes it; shared page renders rule + scenarios + headers + body; unknown token shows not-found; axe check like other screen tests. Run `npm run typecheck && npm run lint && npm test`.

## Docs

- `docs/backend/admin-api.md`: the three endpoints, payloads, error codes.
- `docs/backend/database.md` / `domain-model.md`: `share_token` column.
- `docs/frontend/screens.md`: new public screen (SCR-10 "Shared rule") + the new menu items on SCR-04.
- `CONTEXT.md`: glossary term **Share link** — "A public, revocable, read-only link to one MockRule's live state, for review. _Avoid_: Public rule, published rule."

## Out of scope (follow-ups)

- Comments/annotations on the shared page.
- "Duplicate into my rules" for a signed-in viewer.
- Link expiry.
- Share button on the rule editor page.
