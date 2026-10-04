---
title: Mockan Backend — Implementation plan
status: Draft (v0.1)
date: 2026-10-04
owner: Backend team
related:
  - ../Agent/mockan-architecture.md
  - ../Product/mockan-prd.md
  - ../Frontend/README.md
  - ../panel/src/api/types.ts
audience: Backend engineers and AI coding agents building `server/`
---

# Mockan Backend — Implementation plan

> **Summary:** the ordered, milestone-by-milestone plan to prepare and build the Mockan backend (`server/`: Gateway + Admin API) in Python/FastAPI. It settles the gaps between the [PRD](../Product/mockan-prd.md), the [architecture](../Agent/mockan-architecture.md) and the contract the Panel already ships against ([`panel/src/api/types.ts`](../panel/src/api/types.ts), [Frontend OQ-F1/F4/F5](../Frontend/README.md#open-questions)). Phase 1 = B0–B7; Phase 2 = B8 (only when asked).

## 0. How to use this plan

- Build **one milestone at a time, in order** (B0 → B7 = Phase 1; B8 = Phase 2, **only when asked**). Each milestone ends green on `check` (below), with docs updated in the same change (C-01). It is committed as `B<n>: <summary> (<IDs>)`, matching the Panel's `M<n>` commits.
- `check` = `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run lint-imports && uv run pytest`. It runs from `server/`.
- Sources win over this plan, except where §2 explicitly settles a gap. If code would contradict a `D-xx`, stop and propose a new decision (arch §14 rule 9).
- Backend open questions use `OQ-Bx`. Implement the default and leave a `# TODO(OQ-Bx)` marker.

## 1. Sources of truth

| File | Take from it |
| --- | --- |
| `Product/mockan-prd.md` | Scope, priorities, acceptance checkboxes (PR-01…PR-19), error codes, phases. |
| `Agent/mockan-architecture.md` | Glossary (§2, normative), decisions D-05…D-18, pipeline (§6), matching (§7), schema (§8), Admin routes (§10), config (§12.3), agent rules (§14). |
| `Backend/project-structure.md`, `conventions.md`, `testing.md`, `tech-stack.md` | File placement, import contracts, style, test layers/fixtures, pinned libraries. |
| `panel/src/api/types.ts`, `panel/src/api/client.ts`, `panel/src/mocks/handlers/*.ts`, `Frontend/README.md` (OQ-F1/F4/F5) | **The wire contract the Panel already ships against.** The Admin API MUST match it unless §2 lists a deliberate change. |
| `panel/src/lib/validation.ts`, `panel/src/lib/precedence.ts` | Client-side limits and precedence. Server validation MUST be the same or stricter, never looser. |

## 2. Gaps and conflicts settled by this plan

| # | Gap / conflict | Resolution (default to build) | Doc to update |
| --- | --- | --- | --- |
| G-1 | **Validation error shape.** `Backend/conventions.md` §6 says `errors` is a *list* of `{field, message}`. The Panel (OQ-F1) only parses an `errors` *map* `{field: [msg]}` or FastAPI `detail[]`. | Admin returns `422` problem+json, `code: "validation_failed"`, `errors: {"<camelCase.dotted.path>": ["msg", …]}` (e.g. `responses.0.statusCode`). A global `RequestValidationError` handler converts Pydantic errors to this shape. This closes OQ-F1. | `conventions.md` §6, `testing.md`, `Frontend/README.md` OQ-F1 → resolved |
| G-2 | **Admin payload shapes** (arch §10 lists routes only; OQ-F5). | Adopt the Panel's assumed shapes from `Frontend/README.md` § "OQ-F5 assumed payloads" as the contract (embedded `responses`, `{isEnabled}` toggle bodies, `{updated}` from toggle-all, full-set PUT for service settings, activate returns the rule). Document every route's request/response in new `Backend/admin-api.md`. | `Backend/admin-api.md` (new), arch §10 link |
| G-3 | **Deleting the last MockResponse.** The ER diagram says a rule has 1..n responses. The Panel's MSW sets `activeResponseId = null`. | Reject: `409 code: "last_response"`. A rule always has an active response. Panel follow-up: show the error (MSW gets aligned in the same PR as B6). | `admin-api.md`, Frontend note |
| G-4 | **`publicBaseUrl` for the Panel** (OQ-F4). | `GET /me` adds a read-only `publicBaseUrl` (from `MOCKAN_PUBLIC_BASE_URL`). The Panel keeps its env fallback. | `admin-api.md`, `Frontend/README.md` OQ-F4 |
| G-5 | **New error codes the Panel already uses** but that aren't in arch: `unauthenticated` 401, `forbidden` 403, `not_found` 404, `slug_taken` 409, `slug_immutable` 409, `upstream_host_not_allowed` 422, `validation_failed` 422, `internal_error` 500. | Add all of them, plus `last_response` 409, `developer_disabled` 403, `name_taken`/`path_prefix_taken` 409 (catalog uniqueness) and `environment_exists` 409, to `mockan.domain.errors.ErrorCode`. Gateway codes stay as arch §14 rule 8. | `admin-api.md` § Error codes |
| G-6 | **`X-Mockan-Source` on non-rule responses** (testing.md wants it on error and preflight responses; PR-09 only names `mock \| proxy`). | Mockan problem responses send `error`; Mockan-answered preflight sends `mock`; everything else follows PR-09. `TODO(OQ-B2)`. | `Backend/gateway.md` (new) |
| G-7 | **`mock_rules.service_id` semantics** (an "optional scope" in the ER, never used in §7). | Informational only (Panel grouping/filtering). It does **not** filter matching, because matching runs before Service resolution (§6.2). `TODO(OQ-B1)`. | `gateway.md`, `domain-model.md` |
| G-8 | **Readiness when `degraded`.** | `/_mockan/health/ready`: `503 {"status":"starting"}` until the first snapshot loads; after that `200 {"status":"ready"\|"degraded", "snapshotAgeSeconds": n}`. Degraded stays in rotation (PR-07: keep serving the last good rules). | `gateway.md`, `Backend/operations.md` (new) |
| G-9 | **Local/dev login without an OIDC provider** (OQ-04 is blocking; the Panel has a dev-only login page for MSW). | New setting `MOCKAN_AUTH_MODE = oidc \| dev` (default `oidc`). In `dev`, `GET /api/v1/auth/login?as=<name>&admin=1` signs in as `sso_subject = dev:<name>`. Startup logs a `WARNING` and the docs say MUST NOT be used in shared environments. | arch §12.3 table, `operations.md` |
| G-10 | **Live request-log push across processes** (Phase 2). The Gateway writes logs; the Admin owns the `/hubs/request-log` WebSocket; arch doesn't say how Admin learns about new rows. | **Propose D-19:** after each batch insert, the Gateway's writer sends `pg_notify('mockan_request_logged', '<developerId>:<maxId>')`. The Admin's hub keeps one `LISTEN` connection and pushes rows `> lastId` to that Developer's sockets. Needs approval before B8; no silent deviation. | arch §4 (D-19), §8 |
| G-11 | **Where the Panel is served** (OQ-03). | Admin mounts the built Panel at `MOCKAN_PANEL_BASE_PATH` (default `/`, the separate-host default). The SPA fallback is `index.html` for any GET that is not `/api/*`, `/hubs/*` or a static file. `TODO(OQ-03)`. | arch §12.3, `operations.md` |
| G-12 | **CSRF on cookie-session writes.** | Session cookie `HttpOnly; Secure; SameSite=Lax`. Writes require `Content-Type: application/json`, which a cross-site form can't send without a preflight. The Admin sets no permissive CORS. | `conventions.md` §5 |
| G-13 | **`bodyMode` values before their phase.** | Phase 1 accepts only `Static`; `Template` arrives in B8; `ProxyAndPatch` gets `422` until Phase 3. The DB CHECK already allows all three. | `admin-api.md` |

## 3. Backend open questions (new)

| ID | Question | Default | Marker |
| --- | --- | --- | --- |
| OQ-B1 | Should `mock_rules.service_id` restrict matching to requests resolved to that Service? | No, informational only (G-7). | `matching/matcher.py` |
| OQ-B2 | `X-Mockan-Source` value for Mockan problem responses and preflight? | `error` / `mock` (G-6). | `gateway/problems.py`, `middleware/cors.py` |
| OQ-B3 | Is a Regex rule matched against the original-case path or the lowercased path? | Original case (RE2 search). Authors use `(?i)` for case-insensitive. Exact/Template/Prefix stay case-insensitive per §7.1. | `matching/compile.py` |
| OQ-B4 | Which CI system (GitLab CI / GitHub Actions)? | Ship `server/scripts/check.sh` (the `check` command) and add the pipeline file once the CI system is known. | `server/scripts/check.sh` |
| OQ-B5 | Does `HEAD` match a `GET` rule? | No. The method must equal the rule's method, or the rule's method is `ANY`. | `matching/matcher.py` |

## 4. Milestones (Phase 1)

Each milestone row lists what it builds, the requirements it covers, the tests, and the exit check. Paths are under `server/` unless they start with a top-level folder.

### B0 — Prepare: repo, toolchain, skeleton (C-01, D-14)
- `server/pyproject.toml`:
  - **Phase 1 deps only**, pinned per `tech-stack.md` (no jinja2/faker yet).
  - `[tool.ruff]` with line length 100 and rule sets `E,F,W,I,B,UP,SIM,ASYNC,RUF`.
  - `[tool.mypy] strict = true`.
  - `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and markers `db`, `req`.
  - `[tool.importlinter]`: layers contract `domain` ← `matching` ← `infrastructure` ← {`gateway`, `admin`}, an independence contract `gateway` ⟂ `admin`, and forbidden imports for `matching` (fastapi, starlette, sqlalchemy, asyncpg, httpx) and for `domain` (all third-party).
- `.python-version` (3.14), `uv.lock`, `alembic.ini`, `migrations/env.py` (async, schema `mockan`, `version_table_schema="mockan"`).
- Package skeleton `src/mockan/{domain,matching,infrastructure,gateway,admin}/__init__.py`, each with a one-line docstring. Minimal `create_app()` factories for both apps (they boot and return 404).
- `deploy/compose/docker-compose.yml` with a `postgres:18` service (healthcheck, volume). `server/.env.example` lists every `MOCKAN_*` variable.
- `tests/conftest.py`: registers the `req` marker; adds the `pg_container` session fixture (Testcontainers PG 18 + `alembic upgrade head`).
- `server/scripts/check.sh` (OQ-B4). `.gitignore` covers `.venv`, `src/mockan/admin/static/`, `.env`.
- **Exit:** `uv sync` works from scratch; `check` is green with a smoke test per app (`GET /` → 404); `lint-imports` fails if you add a deliberately bad import (try it once by hand, then remove it).

### B1 — Domain + matching engine (FR-03, FR-04, FR-05, NFR-08, D-17)
- `domain/enums.py`: `MatchType`, `BodyMode`, `RequestSource`, `EnvironmentName`, `AuditAction`, `AuditEntityType`, `ConditionOperator` (PascalCase string values per arch).
- `domain/constants.py`: `SLUG_REGEX`, `RESERVED_SLUGS` (`api`, `hubs`, `health`, plus the rule "starts with `_`"), `MAX_BODY_BYTES = 1_048_576`, `MAX_DELAY_MS = 30_000`, `MAX_REGEX_LENGTH = 512`, status range 100–599, `DEFAULT_PRIORITY = 100`, `SAMPLE_BYTES = 16_384`.
- `domain/errors.py`: `ErrorCode` (gateway codes plus the G-5 codes).
- `domain/validation.py`: `is_valid_slug`, `is_reserved_slug`, `host_is_allowed(host, patterns)`. The `*.x` wildcard matches subdomains only, never the apex; matching is case-insensitive; ports are ignored.
- `matching/template.py`: parser plus compiled matcher.
  - `{name}` matches exactly one non-empty segment.
  - `{*name}` is allowed only as the last segment and matches zero or more segments.
  - Literal segments are case-insensitive.
  - Duplicate parameter names are a parse error.
- `matching/compile.py`, one compiler per match type:
  - Exact: lowercase, strip the trailing `/` except on root.
  - Prefix: lowercase.
  - Regex: `re2.compile` with length and compile checks, original case (OQ-B3).
  - Template.

  `compile_rule()` raises `PatternError(field, message)`. The **Admin reuses it for save-time validation**, so the save check and Gateway behaviour can never disagree.
- `matching/model.py`: frozen dataclasses `CompiledRule`, `CompiledResponse`, `ServiceEntry`, `EnvironmentEntry`, `DeveloperEntry`, and `RequestFacts(method, path, query: Mapping[str, list[str]], headers: Mapping[str(lower), str])`.
- `matching/matcher.py`: `match_request(rules, facts) -> MatchResult | None` with the arch §7.2 key `(priority, TYPE_RANK, -len(pattern), created_at)`.
  - Conditions: query `equals` = any value equals; `exists`; header names are case-insensitive and values case-sensitive.
  - Method rule per OQ-B5.
  - Returns the winner, its captured route params and a reason string (used by test-route in B8).
- `matching/service_resolver.py`: `resolve_service(snapshot, developer, path)`.
  - Picks the longest `PathPrefix` **on a segment boundary**: `/limsa` matches `/limsa` and `/limsa/x` but not `/limsatest`.
  - Picks the environment: the Developer's setting, else the Service default. A missing environment row → `service_not_resolved` with a detail.
  - Builds the upstream path (honours `StripPrefix`).
- `matching/snapshot.py`: immutable `RuleSnapshot`.
  - `developers_by_slug`, `rules_by_developer` (enabled only, pre-compiled, pre-sorted by precedence key), `services_sorted_by_prefix_len`, `built_at`.
  - `RuleSnapshotProvider.current` swaps by attribute assignment.
  - `with_developer_slice(dev_id, ...)` gives cheap partial rebuilds.
- **Tests** (`tests/matching/`, no Docker; every test has `@pytest.mark.req`):
  - Every match type with edge cases (root, trailing slash, unicode/percent-encoded paths, `{*rest}` with zero segments).
  - Every condition kind.
  - Each precedence tiebreak on its own.
  - Isolation across Developers (PR-01).
  - Longest prefix and the segment boundary.
  - StripPrefix true/false.
  - Env fallback.
  - RE2 rejects backreferences, lookaround and > 512 characters.
  - Allowlist wildcard semantics.
  - **Parity table** with `panel/src/lib/precedence.ts`: the same ordered cases produce the same winner.
  - Micro-benchmark (not a CI gate): 500 rules for one Developer, `match_request` p95 < 0.2 ms.
- **Exit:** 100% branch coverage on `mockan.matching` (`pytest --cov=mockan.matching --cov-branch`).

### B2 — Infrastructure: settings, schema, NOTIFY, loader, masking, logging (D-07, D-16, NFR-07, PR-15)
- `infrastructure/settings.py`: `MockanSettings` holds every variable from arch §12.3, plus these new ones, which are added to the arch table in the same PR:
  - `MOCKAN_AUTH_MODE` (`oidc`)
  - `MOCKAN_PANEL_BASE_PATH` (`/`)
  - `MOCKAN_SNAPSHOT_DEBOUNCE_MS` (`200`)
  - `MOCKAN_LOG_LEVEL` (`INFO`)
  - `MOCKAN_LOG_FORMAT` (`json` \| `console`)
- `infrastructure/db/models.py`: arch §8 tables in schema `mockan`. Request logs come in B8.
  - UUIDv7 defaults (`uuid.uuid7`); `created_at`/`updated_at` timestamptz with `server_default=now()` and `onupdate`.
  - Enum columns are `varchar` + `CHECK`.
  - Unique: `developers.slug`, `developers.sso_subject`, `services.name`, `services.path_prefix`, `(service_id, environment)`.
  - Index `(developer_id, is_enabled)` on `mock_rules`.
- **FK delete policy:**

  | FK | On delete |
  | --- | --- |
  | `service_environments.service_id` | CASCADE |
  | `developer_service_settings.*` | CASCADE (a deleted Service or environment falls back to the default; this matches the Panel's MSW) |
  | `mock_rules.service_id` | SET NULL |
  | `mock_responses.rule_id` | CASCADE |
  | `mock_rules.active_response_id` | SET NULL, `use_alter=True` (circular FK) |
  | `mock_rules.developer_id` | RESTRICT |
  | `audit_logs.developer_id` | No FK cascade (keep history) |
- `migrations/versions/<ts>_initial_schema.py`: autogenerated, then reviewed by hand. It creates the `mockan` schema, all CHECKs and `audit_logs`.
- `infrastructure/db/session.py`: engine + `async_sessionmaker(expire_on_commit=False)`.
- `infrastructure/db/notify.py`: a `before_commit` listener.
  - It collects payloads from `session.new | dirty | deleted`: `developers` → the dev id; `mock_rules`/`mock_responses`/`developer_service_settings` → owner dev id; `services`/`service_environments` → `catalog`.
  - It runs `SELECT pg_notify('mockan_config_changed', :p)` once per distinct payload.
  - Bulk `update()` statements (toggle-all) register their payload explicitly through `notify.mark(session, dev_id)`.
- `infrastructure/audit.py`: `record(session, actor, action, entity_type, entity_id, changes)`. It masks `changes` and writes in the same transaction.
- `infrastructure/snapshot_loader.py`: `load_full(session) -> RuleSnapshot` and `load_developer(session, dev_id)`. It uses `selectinload` and compiles through `mockan.matching`. A rule that fails to compile is skipped and logged (it can only come from a bad manual DB edit).
- `infrastructure/masking.py`:
  - `mask_headers` (`Authorization`, `Cookie`, `Set-Cookie` and the `(?i)(token|secret|password|api[-_]?key)` names).
  - `mask_json` (recursive keys).
  - A structlog processor.
- `infrastructure/logging.py`: structlog JSON/console config, bound context vars.
- **Tests** (`@pytest.mark.db`):
  - The migration applies to an empty DB and `alembic check` shows no drift.
  - Model round-trip.
  - NOTIFY fires on commit with the right payloads and **not** on rollback.
  - The loader builds the expected snapshot.
  - The masking table cases.
- **Exit:** `check` is green, including the db tests, and `Backend/database.md` (new) is written.

### B3 — Gateway core: lifespan, snapshot service, health, resolution, CORS, mocks, problems (PR-01, PR-03 CORS part, PR-06, PR-07, PR-09, PR-16, D-07, D-13)
- `gateway/app.py`: `create_app(settings=None, snapshot_provider=None)`.
  - The lifespan starts the shared `httpx.AsyncClient` (B4) and `SnapshotService`, keeps task references and cancels them on shutdown.
  - Test injection skips the DB.
  - Pure-ASGI order per arch §6.2. Health routes are dispatched before resolution.
- `gateway/snapshot_service.py`:
  - A dedicated asyncpg connection with `add_listener` and a debounce (`MOCKAN_SNAPSHOT_DEBOUNCE_MS`).
  - A slice rebuild for a dev id, a full rebuild for `catalog`, a full reload every `MOCKAN_SNAPSHOT_RELOAD_SECONDS`.
  - Reconnects with exponential backoff (capped at 30 s). Each reconnect triggers a full reload, because notifications sent while disconnected are lost.
  - On DB errors it keeps the last snapshot and sets `degraded`.
- `gateway/health.py`: live (always 200) and ready per G-8.
- `gateway/context.py`: `MockanContext(snapshot, developer, path_after_slug, started_at, source, rule_id)` in `scope["state"]["mockan"]`.
- `middleware/cors.py`:
  - Answers preflight with 204 (never forwarded).
  - Glob-matches the Origin against the Developer's `allowed_origins`, falling back to defaults for an unknown slug.
  - Injects headers into every response by wrapping `send`, stripping upstream `Access-Control-*`.
  - Sets `Access-Control-Expose-Headers: X-Mockan-Source, X-Mockan-Rule-Id`, plus `Vary: Origin`.
- `middleware/developer_resolution.py`: `404 developer_not_found` for an unknown or disabled Developer and for reserved slugs.
- `middleware/mock_matching.py`: builds `RequestFacts` from `scope` (no body read), then `match_request`. On a hit it applies `asyncio.sleep(delay_ms)` and writes status/headers/content type/body, plus `X-Mockan-Source: mock` and `X-Mockan-Rule-Id`.
- `gateway/problems.py`: an RFC 7807 builder with `code`, `developer` and `path` (PR-16), and `X-Mockan-Source: error` (OQ-B2).
- `middleware/request_log_capture.py`: a no-op passthrough stub in Phase 1 (arch §6.2 step 2).
- **Tests** (`tests/gateway/`, in-memory snapshot via `snapshot_builder`, ASGITransport):
  - Unknown/disabled slug → 404.
  - Preflight → 204 and never forwarded.
  - Origin echoed only when allowed.
  - Mock status/headers/body/content type/delay. The delay test uses a fake clock or checks ≥ the delay.
  - `X-Mockan-Source` on mock/error/preflight.
  - The problem body has slug and path.
- **Tests** (db): `test_snapshot_service.py`:
  - An insert via SQLAlchemy → the new rule applies in < 2 s (PR-07).
  - DB stopped → keeps serving, `degraded`.
  - DB restarted → recovers.
- **Exit:** a mocked response is served end to end from a rule inserted into Postgres.

### B4 — Gateway proxy: forwarder, transforms, streaming, WebSockets (PR-02, PR-03, PR-04, PR-15, NFR-01, NFR-04, NFR-06, D-15)
- `gateway/proxy/transform.py` (`ProxyTransformer`), **pure functions** over header lists so they can be unit tested. It covers every row of arch §6.3:
  - Path build, raw query string.
  - `Host`, hop-by-hop drop (including headers named in `Connection`).
  - `X-Forwarded-*` and `X-Forwarded-Prefix`, `X-Mockan-Developer`, `ExtraHeaders`, `RewriteOrigin`.
  - `traceparent` passes through.
  - `Location` rewrite when it points at the upstream origin.
  - `Set-Cookie`: drop `Domain`; `Path=/x` → `/{slug}/x`; no Path → `/{slug}`. `TODO(OQ-02)` is noted.
- `gateway/proxy/forwarder.py`:
  - One `httpx.AsyncClient(follow_redirects=False, http2=False, limits=…, timeout=None)` per process. Per-request timeout comes from `ServiceEnvironment.timeout_seconds`.
  - The request body is streamed from ASGI `receive`; the response is streamed with `send(stream=True)` → `aiter_raw()` → `StreamingResponse`. The upstream response is closed in `finally`.
  - The allowlist is checked again before sending (§14 rule 4). A violation gets a `502 upstream_unreachable` problem and an error log.
  - `ConnectError`/`RemoteProtocolError` → 502 `upstream_unreachable`. `TimeoutException` → 504 `upstream_timeout`.
  - Client disconnects cancel the upstream stream.
- WebSocket bridge (`forwarder.py`): accept the ASGI websocket, then connect to `ws(s)://upstream` with `websockets`. Subprotocols and the transformed headers are forwarded. Two pump tasks run until either side closes, and close codes propagate.
- **Tests** (real in-thread Uvicorn `fake_upstream` with echo, `/stream`, `/sse`, `/ws`, `/redirect`, `/set-cookie`, `/slow`, `/download?mb=10`; no httpx mocking):
  - Fidelity of method/path/query/headers/body.
  - Hop-by-hop dropped.
  - 10 MB upload and download with bounded RSS growth (assert < 20 MB delta).
  - SSE events arrive incrementally.
  - WebSocket echo plus close code.
  - Location and Set-Cookie rewrites.
  - Upstream CORS stripped.
  - StripPrefix.
  - Env switch takes effect after a snapshot swap.
  - Unreachable → 502; slow → 504.
  - Non-allowlisted destination refused.
- **Bench** (`server/bench/proxy_overhead.py`, manual, not CI): direct vs via-Gateway latency to `fake_upstream`, target p95 delta ≤ 10 ms (NFR-01). Record the result in `Backend/gateway.md`.
- **Exit:** a Developer with no rules gets identical behaviour to direct upstream for the whole fake-upstream suite (PR-02 acceptance).

### B5 — Admin API foundation: app, auth, problems, `/me`, catalog, service settings (PR-01, PR-03 origins, PR-04, PR-10, PR-15, D-08, D-12)
- `admin/app.py`: `create_app()` with:
  - routers under `/api/v1`, OpenAPI at `/api/v1/openapi.json`;
  - `SessionMiddleware` (signed cookie, G-12);
  - problem handlers;
  - migrate on startup when `MOCKAN_MIGRATE_ON_STARTUP`;
  - static Panel mount + SPA fallback (G-11).
- `admin/auth.py`:
  - Authlib OIDC code flow: `/auth/login` → IdP → `/auth/callback` upserts the `Developer` by `sso_subject` (display name from `name` → `preferred_username` → `email`; `is_admin` when the subject is in `MOCKAN_ADMIN_SSO_SUBJECTS`; default `allowed_origins`). Then it redirects to the Panel.
  - `POST /auth/logout` clears the session (204).
  - Bearer JWT validation via discovery JWKS (audience = client id).
  - Dev mode per G-9.
  - Dependencies: `current_developer` (401 `unauthenticated`); writes on a disabled Developer → 403 `developer_disabled`; `require_admin` (403 `forbidden`).
  - `TODO(OQ-04)` on provider specifics.
- `admin/problems.py`: handlers for `RequestValidationError` → G-1 shape, `DomainError(code, status, field_errors)`, `HTTPException` and catch-all → 500 `internal_error`, which is logged with masking.
- `admin/schemas/`: a `CamelModel` base (`alias_generator=to_camel`, `populate_by_name=True`, `extra="forbid"` on inputs). DTOs mirror `panel/src/api/types.ts` exactly (`Developer` + `publicBaseUrl`, `Service` with embedded `environments`, `ServiceEnvironment`, `DeveloperServiceSetting`).
- `admin/services/` (business rules + audit) and thin `admin/routers/`:
  - `GET /me`.
  - `PUT /me`:
    - The slug can be set only once: `409 slug_immutable`; regex/reserved → 422; taken → `409 slug_taken`, including the DB unique race caught as `IntegrityError`.
    - `displayName` is 1–100 characters.
    - `allowedOrigins` is a list of `scheme://host[:port\|:*]` globs.
  - `GET /services` (everyone) and admin CRUD:
    - `name` matches `^[a-z][a-z0-9-]*$`, unique → `409 name_taken`.
    - `pathPrefix` uses the Panel regex, unique → `409 path_prefix_taken`.
    - `baseUrl` is http(s) with its host allowlisted → `422 upstream_host_not_allowed`.
    - `timeoutSeconds` is 1–3600.
    - A duplicate environment → `409 environment_exists`.
    - `defaultEnvironment` must exist among the environments when set.
  - `GET/PUT /me/service-settings`: a full-set replace. Each `serviceEnvironmentId` must belong to its `serviceId` (422).
  - Every write calls `audit.record` and the NOTIFY hook fires.
- **Tests** (`tests/admin/`, db, `as_developer(slug, is_admin)` override): for every route, the testing.md minimum (happy path, 422 in the G-1 shape, another Developer's resource → 404, non-admin → 403). Also:
  - first-login upsert and admin bootstrap;
  - the slug race;
  - an audit row per write;
  - NOTIFY payload `catalog` vs dev id;
  - OpenAPI snapshot test (`tests/admin/openapi.snapshot.json`), so contract changes show up in diffs.
- **Exit:** the Panel with `VITE_USE_MSW=false` (plus the Vite dev proxy from B7) can log in (dev mode), claim a slug, edit origins, and list and administer the catalog.

### B6 — Admin API rules and responses (PR-05, PR-06, PR-08, PR-11 data model, PR-15 audit, FR-11)
- Routes per arch §10 / G-2:
  - `GET/POST /me/rules`, `GET/PUT/DELETE /me/rules/{id}`.
  - `POST …/toggle` with `{isEnabled}` (idempotent) → rule.
  - `POST /me/rules/toggle-all` with `{isEnabled}` → `{updated}`, as one bulk UPDATE plus `notify.mark`.
  - `POST/PUT/DELETE …/responses[/{responseId}]`; DELETE of the last response → `409 last_response` (G-3).
  - `POST …/activate` → rule.
- Validation:
  - `compile_rule()` from B1, with field errors mapped to `pattern`.
  - `method` ∈ ANY/GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS; `name` 1–200; `priority` int ≥ 0.
  - Conditions `{key, operator, value?}`: `value` is required for `equals`; keys are non-empty.
  - `serviceId` must exist or be null.
  - Responses: `name` 1–100, `statusCode` 100–599, `delayMs` 0–30000, `body` ≤ 1 MiB (UTF-8 bytes), `headers` string→string, `contentType` non-empty, `bodyMode` per G-13.
  - The server does **not** reject invalid JSON bodies; that check belongs to the Panel (PR-06), so intentionally malformed payloads stay possible.
- Create inserts the rule and responses in one transaction, sets `active_response_id` to the first response, and writes one `create` audit row with masked changes.
- **Tests:**
  - CRUD, isolation (B can't see A's rule → 404) and every validation rule;
  - toggle idempotency and toggle-all count;
  - activate;
  - last-response 409;
  - audit actions `create/update/delete/toggle/activate`;
  - **cross-process PR-07 test**: Admin `POST /me/rules` → the running Gateway app (with a real SnapshotService on the same PG) serves the mock within 2 s; then toggle-off → proxied within 2 s.
- Panel alignment in the same PR: update the MSW handler for G-3 and keep `Frontend/README.md` OQ-F5 in sync (only if something differs from what's assumed).
- **Exit:** the Panel's full M3 flows work against the real Admin API.

### B7 — Integration, packaging, Phase 1 exit (PR-17 health part, NFR-03, NFR-05, §12.3)
- `deploy/docker/gateway.Dockerfile` and `admin.Dockerfile`:
  - `python:3.14-slim`, multi-stage, `uv sync --frozen --no-dev`, non-root user;
  - entrypoints per arch §12.3;
  - the Admin image builds `panel/` (`npm ci && npm run build:server`) in a node stage and copies it into `mockan/admin/static/`.
- `deploy/compose/docker-compose.yml`: `postgres`, `admin` (migrate on startup, `MOCKAN_AUTH_MODE=dev`), `gateway` (2 replicas to prove NFR-03), and an optional `fake-upstream` for demos.
- `panel/vite.config.ts`: add `server.proxy` for `/api` and `/hubs` → `http://localhost:8081` when `VITE_USE_MSW=false`. This is a small Panel change and updates `Frontend/README.md`.
- Phase 1 acceptance suite (`tests/acceptance/`, db): one test per row of `Backend/testing.md` §5 (PR-01…PR-16), named by PR ID, plus the PRD §6 journey scripted end to end over HTTP:
  1. Dev login.
  2. Claim the slug.
  3. Proxied token call to `fake_upstream`.
  4. Create the Exact rule `GET /limsa/api/v1/dashboard`.
  5. The mock is served within 2 s with `X-Mockan-Source: mock`.
  6. Disable it → proxied.
- Optional: run the Panel Playwright journey against the compose stack instead of MSW.
- Docs (C-01), all in this milestone if not already written:
  - `Backend/gateway.md`, `admin-api.md`, `database.md`, `domain-model.md`, `operations.md` (config table, deploy, migrations policy, runbook: degraded readiness, LISTEN reconnects, how to add a Service);
  - `Backend/README.md` quick facts → "Phase 1 complete";
  - arch §12.3 new settings and §15 change log entry v1.2 (G-items + D-19 proposal);
  - `Frontend/README.md` OQ-F1/F4/F5 marked resolved, with links.
- **Exit = Phase 1 exit (PRD §11):** the compose stack runs; the acceptance suite is green; every PRD P0 checkbox maps to a passing test (`pytest -m req --collect-only -q` lists PR-01…PR-16). **Stop and ask for review before B8.**

## 5. Phase 2 — B8 (only when asked; needs D-19 approved)

| Step | Scope | Key points |
| --- | --- | --- |
| B8a Request log | PR-12, FR-09, D-18, D-19 | `request_logs` migration. `RequestLogCaptureMiddleware` wraps `receive`/`send` to tee ≤ 16 KB samples without buffering (§14 rule 3). `asyncio.Queue(maxsize)` with `put_nowait`, drop and count. A batch writer (size/interval) masks before insert, then `pg_notify('mockan_request_logged', …)`. Retention job: 7 days **and** 5,000 rows per Developer. `GET /me/request-logs?cursor=&source=&path=` (keyset on id). `POST /me/request-logs/{id}/create-rule`. WebSocket `/hubs/request-log` (session-cookie auth, per-Developer fan-out from one LISTEN). New settings `MOCKAN_REQUEST_LOG_QUEUE_SIZE`, `_BATCH_SIZE`, `_FLUSH_MS`. |
| B8b Test route | PR-13, FR-10 | `POST /me/test-route` builds that Developer's snapshot slice through `snapshot_loader.load_developer` and calls the **same** `match_request`/`resolve_service`. Returns `{outcome: mock\|proxy\|error, rule?, reason, upstreamUrl?, errorCode?}`. A parity test drives identical cases through the Gateway and test-route. |
| B8c Templated bodies | PR-19 | Add `jinja2` and `faker`. A `SandboxedEnvironment` template is compiled at snapshot build. Context: `request.path/query/headers`, `route.<param>`, `fake.*`. Render errors → `mock_render_failed` problem with the message. Rendering runs on the event loop with a size cap; benchmark it. |
| B8d Export / import | PR-14, FR-12 | `GET /me/rules/export` (versioned JSON `{version: 1, rules: [...]}`, no ids). `POST /me/rules/import?mode=merge\|replace` validates everything first and saves all or nothing, reporting per-entry errors in the G-1 shape. |
| B8e Operability | PR-17 | OpenTelemetry metrics `mockan_requests_total{source}`, `mockan_proxy_duration_ms`, `mockan_snapshot_age_seconds`, `mockan_request_log_dropped_total`. FastAPI/httpx instrumentation. Bound `trace_id` in logs. |

## 6. Cross-cutting rules (checklist on every milestone PR)

- [ ] Glossary names only; no `tenant` (D-01).
- [ ] No DB access, full-body reads, sync I/O or `time.sleep` on the Gateway request path (§14 rules 2, 3, 10).
- [ ] Every Gateway response sets `X-Mockan-Source` (§14 rule 7).
- [ ] Problem codes come from `ErrorCode` only (§14 rule 8).
- [ ] New tests carry `@pytest.mark.req("<ID>")`; matching/transform changes have tests (§14 rule 6).
- [ ] Admin `/me/*` queries are filtered by `current_developer.id`; catalog writes need `require_admin`; every config write is audited in the same transaction.
- [ ] New settings are added to arch §12.3; new routes or payload changes to `admin-api.md` and the OpenAPI snapshot; schema changes to `database.md` + an Alembic migration.
- [ ] `TODO(OQ-xx)` markers sit at the exact spot for every defaulted open question.

## 7. Risks specific to the build

| Risk | Mitigation |
| --- | --- |
| Streaming breaks silently (something buffers). | The RSS-bounded 10 MB tests and the SSE incremental test in B4. Pure-ASGI middleware only. |
| A LISTEN connection drop loses notifications. | A full reload on every reconnect, plus the 60 s periodic reload, plus the snapshot-age readiness field. |
| Admin validation and Gateway behaviour drift apart. | One compiler (`mockan.matching.compile_rule`) used by both. Parity tests with the Panel's `precedence.ts`. |
| The Panel contract drifts from the backend. | The OpenAPI snapshot test. Follow-up: generate `panel/src/api/types.ts` with `openapi-typescript` from `/api/v1/openapi.json`. |
| OQ-04 (IdP) stays unanswered and blocks login testing. | Dev auth mode (G-9) unblocks everything but the real SSO wiring. |
| google-re2 or asyncpg wheels lag on cp314. | Check in B0 (`uv sync` on CI image). Fallback: pin a Python 3.13 image temporarily, behind a new decision. |

