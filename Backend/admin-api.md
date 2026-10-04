---
title: Mockan Backend — Admin API
status: Draft (v0.1, B5 foundation: auth, /me, catalog, service settings)
date: 2026-10-04
owner: Backend team
related:
  - ../Agent/mockan-architecture.md
  - implementation-plan.md
  - conventions.md
  - database.md
  - ../panel/src/api/types.ts
audience: Backend engineers, Panel engineers and AI coding agents
---

# Mockan Backend — Admin API

> **Summary:** what the control plane serves today, what every route accepts and returns, the validation limits, the error codes and the decisions that are not obvious from the code. The route list is [architecture §10](../Agent/mockan-architecture.md#10-admin-api-control-plane); the wire contract is the one the Panel ships against ([`panel/src/api/types.ts`](../panel/src/api/types.ts)); the live schema is `/api/v1/openapi.json`, pinned by `server/tests/admin/openapi.snapshot.json`. Rules and responses (`/me/rules*`) arrive in B6, the request log and test route in Phase 2.

## 1. Conventions

| Topic | Rule |
| --- | --- |
| Base path | `/api/v1`. OpenAPI at `/api/v1/openapi.json`, Swagger UI at `/api/v1/docs`. |
| JSON | camelCase on the wire (`CamelModel`, `alias_generator=to_camel`). Inputs use `extra="forbid"`: an unknown field is a `422`, so a client can never set `isAdmin`, `id` or `developerId` by adding a field. |
| Ids / times | UUIDv7 strings; UTC ISO-8601 with `Z`. |
| Writes | `Content-Type: application/json` is required (FastAPI rejects other types with `422`). With `SameSite=Lax` and no CORS on the Admin this is the CSRF defence (G-12). |
| Idempotent writes | A `PUT` that changes nothing writes nothing: no audit row and no `pg_notify`. |
| Ownership | `/me/*` handlers only see the signed-in Developer's data. An id that doesn't exist **or isn't yours** is `404 not_found`, never `403`. A malformed id (not a UUID) is also `404`. |
| Audit | Every config write adds one `audit_logs` row in the same transaction (`changes` is `{field: {"from", "to"}}` for updates and the new values for creates; masked, NFR-07). |
| Gateway notification | ORM writes fire `pg_notify('mockan_config_changed', …)` on commit ([database.md §3](database.md#3-change-notification-d-07-fr-08)): the Developer id for `/me/*`, `catalog` for Service writes. |

## 2. Authentication

Two ways in, one dependency (`current_developer`, `admin/auth.py`): the session cookie wins over a bearer token.

| Mechanism | Used by | How |
| --- | --- | --- |
| Session cookie `mockan_session` | The Panel | `GET /auth/login` → IdP → `GET /auth/callback` sets it. Signed (`MOCKAN_SESSION_SECRET`), `HttpOnly`, `SameSite=Lax`, `Secure` (except in dev mode), 7 days. |
| `Authorization: Bearer <JWT>` | API clients | Validated against the provider's discovery document and JWKS: asymmetric algorithms only, `iss` = the discovered issuer, `aud` contains `MOCKAN_OIDC_CLIENT_ID`, `exp` and `sub` required, 60 s leeway. An unknown `kid` triggers one JWKS refetch (key rotation). `TODO(OQ-04)`: which claim carries the audience of an access token is provider-specific. |

The first request of a new subject creates the Developer (display name from `name` → `preferred_username` → `email`, else `Developer`; `allowedOrigins` = `MOCKAN_DEFAULT_ALLOWED_ORIGINS`) and writes a `create` audit row. Parallel first requests are safe: the unique `sso_subject` decides and the loser re-reads.

**Admins.** `is_admin` is set when the subject is in `MOCKAN_ADMIN_SSO_SUBJECTS`: on creation, and as a **promotion** on any later login. A login never removes admin rights.

**Dependencies** (all in `admin/auth.py`):

| Dependency | Passes when | Otherwise |
| --- | --- | --- |
| `current_developer` | A valid session or bearer token | `401 unauthenticated` |
| `writable_developer` | …and `is_enabled` | `403 developer_disabled` |
| `require_admin` | …and writable and `is_admin` | `403 forbidden` |

A **disabled** Developer can still read (`GET /me` returns `isEnabled: false`, which the Panel shows as "workspace disabled") but every write is `403 developer_disabled`.

### Dev mode (G-9)

`MOCKAN_AUTH_MODE=dev` removes the identity provider so everything can be developed and tested without one (OQ-04). It logs a `WARNING` at startup and **MUST NOT be used in shared environments**: anyone who can reach the Admin can sign in as anyone.

- `GET /auth/login?as=<name>&admin=1` signs in as `sso_subject = dev:<name>` and redirects to the Panel. `as` defaults to `dev` and must match `^[A-Za-z0-9._-]{1,50}$`; `admin=1` makes that Developer an admin.
- The bare `GET /auth/login` (what the Panel calls) therefore signs in as `dev:dev`. To make that user an admin, set `MOCKAN_ADMIN_SSO_SUBJECTS=["dev:dev"]`.
- `/auth/callback` is `404`; bearer tokens are `401`; the session secret may be empty (a random one is used, so sessions end with the process). In `oidc` mode the three `MOCKAN_OIDC_*` variables and a 32+ character `MOCKAN_SESSION_SECRET` are required and the app **refuses to start** without them.

## 3. Routes

"Admin" = `require_admin`. "Writer" = `writable_developer`. Error codes are in §5.

| Method | Route | Auth | Request → response | Notes |
| --- | --- | --- | --- | --- |
| GET | `/auth/login` | — | → `303` | OIDC: to the IdP (authorization code + PKCE S256). Dev mode: signs in and goes to the Panel. |
| GET | `/auth/callback` | — | → `303` | Exchanges the code, verifies the ID token (signature, issuer, audience, expiry, nonce), starts the session, goes to the Panel. Failure → `401`. |
| POST | `/auth/logout` | — | → `204` | Clears the session; idempotent. `TODO(OQ-04)`: no RP-initiated logout at the IdP, so SSO may sign the user straight back in. |
| GET | `/me` | session | → `Developer` | Includes `publicBaseUrl` (G-4). |
| PUT | `/me` | Writer | `DeveloperUpdate` → `Developer` | See §4.1. |
| GET | `/services` | session | → `Service[]` | Sorted by name, environments sorted `dev`, `stage`. Everyone can read. |
| POST | `/services` | Admin | `ServiceInput` → `201 Service` | `environments` is `[]`; add them with the routes below. |
| PUT | `/services/{id}` | Admin | `ServiceInput` → `Service` | |
| DELETE | `/services/{id}` | Admin | → `204` | Environments and Developers' settings cascade; rules keep existing with `serviceId: null`. |
| POST | `/services/{id}/environments` | Admin | `ServiceEnvironmentInput` → `201 ServiceEnvironment` | |
| PUT | `/services/{id}/environments/{envId}` | Admin | `ServiceEnvironmentInput` → `ServiceEnvironment` | |
| DELETE | `/services/{id}/environments/{envId}` | Admin | → `204` | Settings that chose it cascade (the Developer falls back to the default). The Service's **default** environment can't be deleted (§6). |
| GET | `/me/service-settings` | session | → `DeveloperServiceSetting[]` | `[{serviceId, serviceEnvironmentId}]`; a Service with no entry uses its default environment. |
| PUT | `/me/service-settings` | Writer | `DeveloperServiceSetting[]` → `DeveloperServiceSetting[]` | **Replaces the whole set** (G-2). `[]` clears it. |
| — | `/me/rules*`, `…/responses*` | | | B6 |
| — | `/me/test-route`, `/me/request-logs*`, `/me/rules/export|import`, `/hubs/request-log` | | | Phase 2 (B8) |

## 4. Payloads and validation

Field limits live in `mockan.domain.constants` (shared with the Gateway) and `admin/schemas/`. The server is the same as or stricter than the Panel's `checks.ts`, never looser. A field error is keyed by the camelCase dotted path of the field (`allowedOrigins.1`, `0.serviceEnvironmentId`); the Panel maps these onto its form fields.

### 4.1 `Developer` and `DeveloperUpdate`

`Developer` = `id`, `slug` (`null` until claimed), `displayName`, `allowedOrigins`, `isEnabled`, `isAdmin`, `createdAt`, `updatedAt`, `publicBaseUrl`.

`DeveloperUpdate` has three optional fields; `null` or absent means "leave it":

| Field | Rule |
| --- | --- |
| `slug` | Settable **once** (PR-01). Already set to something else → `409 slug_immutable`; sending the current slug is a no-op. Otherwise `^[a-z][a-z0-9-]{1,31}$`, not `_*`, `api`, `hubs`, `health` → else `422` (messages as the Panel's `slugProblem`); taken → `409 slug_taken` (also when the unique index decides a race). |
| `displayName` | Trimmed, 1–100 characters. |
| `allowedOrigins` | At most 50 entries. Each is `scheme://host[:port]` where the port may be `*` and the host may start with `*.`, e.g. `http://localhost:*`, `https://*.dev.internal`; no path, no spaces, ≤ 255 characters. Stored trimmed. |

Order of checks: unknown field / structure (`422`) → slug immutability (`409`) → slug validity (`422`) → slug availability (`409`). Field errors from Pydantic and the slug rules can therefore arrive in two rounds.

### 4.2 Catalog

`Service` = `id`, `name`, `pathPrefix`, `stripPrefix`, `rewriteOrigin`, `defaultEnvironment`, `environments: ServiceEnvironment[]`, `createdAt`, `updatedAt`. `ServiceEnvironment` = `id`, `serviceId`, `environment`, `baseUrl`, `timeoutSeconds`, `extraHeaders`, `createdAt`, `updatedAt`.

| Field | Rule |
| --- | --- |
| `name` | `^[a-z][a-z0-9-]*$`, ≤ 100. Unique → `409 name_taken`. |
| `pathPrefix` | One or more non-empty segments of `[A-Za-z0-9._~-]`, each starting with `/`, no trailing `/`, ≤ 200 (`/limsa`, `/api/limsa`). Unique **case-insensitively** → `409 path_prefix_taken`. |
| `stripPrefix`, `rewriteOrigin` | Real booleans (`"yes"`, `1` are `422`); default `false`. |
| `defaultEnvironment` | `dev` or `stage`; default `stage`. |
| `environment` | `dev` or `stage`; one per Service → `409 environment_exists` (also when renaming onto a sibling). |
| `baseUrl` | `http(s)://host[:port][/path]`, ≤ 2048; **no credentials, query string or fragment** → `422 validation_failed`. The host must match `MOCKAN_ALLOWED_UPSTREAM_HOSTS` (case-insensitive, port ignored, `*.x` matches subdomains only, never `x`) → else `422 upstream_host_not_allowed` with `errors.baseUrl` (PR-15, NFR-06). Stored as sent (trimmed). The Gateway checks again before every request. |
| `timeoutSeconds` | Integer 1–3600 (not a bool or float); default 100. |
| `extraHeaders` | At most 50; names are HTTP tokens; values contain no `\r`, `\n` or NUL. **Returned in clear to every signed-in Developer** (the catalog is readable by all): never put production secrets in them. They are masked in `audit_logs`. |

### 4.3 `DeveloperServiceSetting`

Each entry's `serviceEnvironmentId` must belong to its `serviceId`, each Service may appear once, and both ids must exist; otherwise one `422` lists every problem (`0.serviceId`: unknown Service, `1.serviceEnvironmentId`: wrong Service, `1.serviceId`: listed twice). Nothing is written on error. Only changed rows are written, in one transaction with one `update` audit row (`developer_service_setting`, entity id = the Developer's id, `changes.settings = {from, to}` as `{serviceId: serviceEnvironmentId}`).

## 5. Errors

Every error is `application/problem+json`, `Cache-Control: no-store`:

```json
{
  "type": "https://mock.novin-tools.com/problems/validation_failed",
  "title": "Some fields need attention",
  "status": 422,
  "code": "validation_failed",
  "detail": "…only when there is something to say beyond the fields…",
  "errors": { "allowedOrigins.1": ["Start with http:// or https://."] }
}
```

`type` is built from `MOCKAN_PUBLIC_BASE_URL`. `errors` is a map `{"<camelCase.dotted.path>": ["message", …]}` and is present only when there are field errors (G-1: this closes Frontend OQ-F1). A request body that is not valid JSON is `422` with `detail: "The request body isn't valid JSON."` and no `errors`. Admin responses do **not** carry `X-Mockan-Source` (that is the Gateway's).

| Code | Status | When |
| --- | --- | --- |
| `unauthenticated` | 401 | No valid session or bearer token; a failed OIDC callback. |
| `forbidden` | 403 | Not an admin. |
| `developer_disabled` | 403 | A write by a disabled Developer. |
| `not_found` | 404 | Unknown or foreign id, malformed id, unknown route. |
| `validation_failed` | 422 | Field errors. Also any other 4xx FastAPI raises on its own (e.g. `405`, with its `Allow` header). |
| `upstream_host_not_allowed` | 422 | `baseUrl` host outside the allowlist. |
| `slug_taken` | 409 | The slug belongs to another Developer. |
| `slug_immutable` | 409 | The Developer already has a different slug. |
| `name_taken` | 409 | Service name in use. |
| `path_prefix_taken` | 409 | Service PathPrefix in use (case-insensitive). |
| `environment_exists` | 409 | The Service already has that environment. |
| `last_response` | 409 | B6: deleting a rule's last response (G-3). |
| `internal_error` | 500 | Unhandled exception. Logged through structlog (masked); the body never carries internals. |

Gateway codes (`developer_not_found`, …) are listed in [gateway.md](gateway.md).

## 6. Decisions and deliberate differences

- **Parallel writes are safe.** Pre-checks give friendly `409`s; a race that slips past them is caught as the unique-constraint `IntegrityError` (`uq_developers_slug`, `uq_services_name`, `uq_services_path_prefix`, `uq_service_environments_service_id_environment`) and becomes the same `409`. Tests run both as real parallel requests.
- **`defaultEnvironment` vs. existing environments (`OQ-B6`).** The plan said it "must exist among the environments when set". The Panel's save order (`useSaveService`) is: save the Service, then delete, update and create its environments, so a new Service has no environments yet and a switched default may point at one that is about to be created. Enforcing it on `POST`/`PUT /services` would break that flow. Default implemented: **not enforced on Service writes** (a dangling default shows up as `service_not_resolved` at request time), and enforced where it can't break the Panel: **deleting the environment that is the Service's default is `422`** ("Choose another default first."). Marker: `TODO(OQ-B6)` in `services/catalog.py`.
- **Error keys are camelCase.** The MSW handlers return some snake_case keys (`path_prefix`, `base_url`); the Panel's client converts either, and the real API sends only camelCase.
- **`PUT` bodies.** `PUT /services/{id}` takes the Service fields only (no `environments`), as the Panel sends them. Omitted booleans and `defaultEnvironment` take the database defaults rather than keeping the old value: it is a full replace, like the Panel's form.
- **Session cookie in dev mode is not `Secure`.** Dev mode runs over plain `http` on localhost, where a `Secure` cookie isn't sent back by every client. In `oidc` mode it is `Secure` (G-12).
- **Migrations on startup.** `MOCKAN_MIGRATE_ON_STARTUP=true` runs `alembic upgrade head` in the lifespan, before the app serves (non-prod only; shared environments use a migration job, [database.md §4](database.md#4-migrations)). It needs `alembic.ini` next to `migrations/`, i.e. a source checkout or an editable install.

## 7. Serving the Panel (G-11, OQ-03)

If `src/mockan/admin/static/index.html` exists (the Panel build, git-ignored), the Admin serves it under `MOCKAN_PANEL_BASE_PATH` (default `/`):

- A file that exists is served as is; any other path **without a file extension** gets `index.html` (`Cache-Control: no-cache`) so client-side routes survive a reload; a missing path **with** an extension (`/assets/old.js`) is `404`.
- With the base path `/`, anything under `/api/` or `/hubs/` that isn't a route is a problem `404`, never the app shell.
- With another base path (e.g. `/_mockan/admin`) only that prefix is served; `/api/v1/*` stays at the root and sign-in lands on the Panel at `<base>/`.
- Without a build the Admin is API-only. `TODO(OQ-03)`.

## 8. Tests

`server/tests/admin/` (Testcontainers PostgreSQL; `@pytest.mark.db`):

| File | Covers |
| --- | --- |
| `test_problems.py` | The problem shape, `errors` map, JSON-only writes, malformed ids, 500 without internals. |
| `test_auth_dev.py` | Dev login, sessions, first-login upsert, admin bootstrap/promotion, parallel first logins, disabled Developers. |
| `test_auth_oidc.py` | The real code flow (PKCE, state) and bearer validation against `tests/support/fake_idp.py` (a live provider on a real socket): wrong audience/issuer, expiry, unknown key, key rotation, HS256 confusion, unreachable provider, startup misconfiguration. |
| `test_me_api.py`, `test_services_api.py`, `test_service_settings_api.py` | Every route: happy path, `422` shape, other Developer's data, non-admin `403`, audit rows, `pg_notify` payloads, races. |
| `test_panel.py` | Static files, SPA fallback, base path, path traversal. |
| `test_openapi.py` | `openapi.snapshot.json`; every `422` is the `Problem` schema. Regenerate with `UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/admin/test_openapi.py` and update `panel/src/api/types.ts` in the same change. |
| `test_app.py` | The lifespan: migrate on startup (and not by default). |
