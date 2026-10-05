---
title: Mockan Backend — Operations
status: Draft (v0.1, Phase 1)
date: 2026-10-04
owner: Backend team
related:
  - ../agent/mockan-architecture.md
  - gateway.md
  - admin-api.md
  - database.md
audience: Engineers deploying and running Mockan, and AI coding agents
---

# Mockan Backend — Operations

> **Summary:** how to run the stack (compose and images), every `MOCKAN_*` setting, health and readiness, migrations, the runbook for the situations that will happen, and how to add a Service. Design context: [architecture §12](../agent/mockan-architecture.md#12-security-operations-and-deployment).

## 1. Run it locally (compose)

```bash
cd deploy/compose
docker compose up --build                  # postgres + admin (with the Panel) + 2 gateways
docker compose --profile demo up --build   # ...plus a demo upstream (`fake-upstream:9000`)
MOCKAN_DB_PORT=55433 docker compose up -d  # when 5432 is taken
```

| What | Where |
| --- | --- |
| Panel + Admin API | `http://localhost:8765` (nginx; `MOCKAN_PORT` to change; Admin API under `/api`) |
| Gateway replicas | `http://localhost:8765/mock` (nginx round-robins both replicas; same database, own snapshot each: NFR-03) |
| PostgreSQL | `localhost:${MOCKAN_DB_PORT:-5432}`, user/password/db `mockan` |

The stack runs `MOCKAN_AUTH_MODE=dev` (no identity provider; G-9). The bare sign-in is `dev:dev`, which the compose file lists in `MOCKAN_ADMIN_SSO_SUBJECTS`, so it is an admin. **Never use dev mode in a shared environment.** The Admin applies the migrations on startup (`MOCKAN_MIGRATE_ON_STARTUP=true`); the Gateways wait for the Admin to be healthy.

The PRD §6 journey by hand (the `demo` profile registers nothing; do it through the Panel or the API):

```bash
A=http://localhost:8765; H='content-type: application/json'
curl -c jar -s "$A/api/v1/auth/login" -o /dev/null                       # sign in as dev:dev
curl -b jar -X PUT -H "$H" -d '{"slug":"ehtesham"}' $A/api/v1/me          # claim the slug
curl -b jar -X POST -H "$H" -d '{"name":"limsa","pathPrefix":"/limsa"}' $A/api/v1/services   # note its id
curl -b jar -X POST -H "$H" -d '{"environment":"stage","baseUrl":"http://fake-upstream:9000"}' $A/api/v1/services/<id>/environments
curl -i http://localhost:8765/mock/ehtesham/limsa/api/v1/dashboard             # X-Mockan-Source: proxy
```

Panel development against a real Admin: run the Admin on 8081, then `VITE_USE_MSW=false npm run dev` in `panel/`. The Vite dev server proxies `/api` and `/hubs` to `http://localhost:8081` (`MOCKAN_ADMIN_URL` overrides the target), so the session cookie stays same-origin.

## 2. Images

Build from the **repository root**:

```bash
docker build -f deploy/docker/gateway.Dockerfile -t mockan-gateway .
docker build -f deploy/docker/admin.Dockerfile   -t mockan-admin .
#   Panel on another path (OQ-03): --build-arg PANEL_BASE_PATH=/_mockan/admin/  + MOCKAN_PANEL_BASE_PATH at runtime
```

Both are `python:3.14-slim`, multi-stage, `uv sync --frozen --no-dev`, run as a non-root user (uid 10001) and have a `HEALTHCHECK`. The Admin image builds `panel/` in a Node stage and copies it to `mockan/admin/static/`. Entry points are the ones in arch §12.3. The Gateway reads `FORWARDED_ALLOW_IPS` itself (Uvicorn): set it to the ingress CIDRs; the default is `127.0.0.1`.

## 2a. Deploying from GHCR (`deploy/compose/deploy.sh`)

CI publishes `ghcr.io/modarreszadeh/mockan/admin` and `/gateway` (`linux/amd64`; tags `latest`, `main`, the commit SHA). `deploy/compose/docker-compose.prod.yml` layers production settings over the local compose file: the GHCR images instead of a build, `MOCKAN_AUTH_MODE=oidc`, a required database password and session secret, `MOCKAN_MIGRATE_ON_STARTUP=false`, no published PostgreSQL port, restart policies and rotated JSON logs. Only nginx is published, on `MOCKAN_BIND:MOCKAN_PORT` (default `127.0.0.1:8765`); terminate TLS in front of it.

```bash
cd deploy/compose
./deploy.sh --dry-run     # validate .env, render the config, print the plan; changes nothing
./deploy.sh [<tag>]       # pull, start PostgreSQL, migrate, restart, probe through nginx
./deploy.sh --rollback    # redeploy the tag recorded in .last-deployed-tag (images only)
./deploy.sh --check-db    # alembic current / heads
```

`deploy.sh` owns `.env`: it creates it from `.env.production.example`, generates empty `POSTGRES_PASSWORD` and `MOCKAN_SESSION_SECRET` values without printing them, validates the rest, and lists what is still missing (`MOCKAN_OIDC_ISSUER`, `_CLIENT_ID`, `_CLIENT_SECRET`, `MOCKAN_ADMIN_SSO_SUBJECTS`, `MOCKAN_ALLOWED_UPSTREAM_HOSTS`, `MOCKAN_PUBLIC_BASE_URL`). A deploy runs the steps in this order: pull, start PostgreSQL, stop nginx, Gateways and Admin, `alembic upgrade head`, start everything and wait for the health checks, probe `/api/v1/openapi.json` and `/mock/_mockan/health/live` through nginx. A failed pull stops before anything is touched; a failed migration restarts the previous containers. The first deploy creates the database with the generated password, so changing `POSTGRES_PASSWORD` later does not change an existing database. Compose files and `nginx.conf` come from the checkout: `git pull` before deploying when they changed.

## 3. Settings

All are environment variables with the `MOCKAN_` prefix (`infrastructure/settings.py`, the only place that reads the environment; `server/.env.example` lists them). The table is arch §12.3.

| Variable | Used by | Default | Notes |
| --- | --- | --- | --- |
| `MOCKAN_DATABASE_URL` | both | `postgresql+asyncpg://mockan:mockan@localhost:5432/mockan` | |
| `MOCKAN_ALLOWED_UPSTREAM_HOSTS` | both | `[]` | JSON list; `*.x` matches subdomains only. Empty = nothing can be saved or proxied. **Never list production hosts** (NFR-06). |
| `MOCKAN_PUBLIC_BASE_URL` | both | `https://mock.novin-tools.com` | `Location` rewrite; returned as `publicBaseUrl` by `GET /me`. With Compose, set it in `deploy/compose/.env`. |
| `MOCKAN_DEFAULT_ALLOWED_ORIGINS` | both | `["http://localhost:*","http://127.0.0.1:*"]` | New Developers' `allowedOrigins`; Gateway fallback for unknown slugs. |
| `MOCKAN_LOG_LEVEL`, `MOCKAN_LOG_FORMAT` | both | `INFO`, `json` | `console` for local reading. |
| `MOCKAN_OTEL_ENDPOINT`, `MOCKAN_OTEL_EXPORT_INTERVAL_SECONDS` | both | empty, `30` | OTLP/HTTP collector for metrics (and spans); empty = no export. |
| `MOCKAN_TRACING_ENABLED` | both | `false` | Opt-in tracing (see §4a). |
| `MOCKAN_AUTH_MODE` | admin | `oidc` | `dev` = no identity provider, local only. |
| `MOCKAN_OIDC_ISSUER`, `_CLIENT_ID`, `_CLIENT_SECRET` | admin | empty | Required in `oidc` mode; the Admin **refuses to start** without them. Keycloak: see [§3a](#3a-sign-in-with-keycloak-oq-04). |
| `MOCKAN_SESSION_SECRET` | admin | empty | ≥ 32 random characters outside dev mode; same value on every Admin replica. |
| `MOCKAN_ADMIN_SSO_SUBJECTS` | admin | `[]` | Subjects that are admins (on creation and as a promotion at later logins; never demoted). |
| `MOCKAN_MIGRATE_ON_STARTUP` | admin | `false` | Non-prod only. |
| `MOCKAN_PANEL_BASE_PATH` | admin | `/` | Where the built Panel is served. `TODO(OQ-03)`. |
| `MOCKAN_SNAPSHOT_RELOAD_SECONDS` | gateway | `60` | Safety-net full reload. |
| `MOCKAN_SNAPSHOT_DEBOUNCE_MS` | gateway | `200` | Coalesces notifications. |
| `MOCKAN_REQUEST_LOG_QUEUE_SIZE` | gateway | `10000` | Bounded; when full the Gateway drops the entry and counts it (never slows a request). |
| `MOCKAN_REQUEST_LOG_BATCH_SIZE`, `_FLUSH_MS` | gateway | `200`, `500` | Writer batching. |
| `MOCKAN_REQUEST_LOG_RETENTION_DAYS`, `_MAX_ROWS_PER_DEVELOPER`, `_CLEANUP_SECONDS` | gateway | `7`, `5000`, `600` | Retention job (one Gateway prunes at a time, advisory lock). |

## 3a. Sign in with Keycloak (OQ-04)

**Locally**, a Keycloak is one command away (realm `internal`, client `mockan`, PKCE S256, an audience mapper):

```bash
cd deploy/compose
docker compose -f docker-compose.yml -f docker-compose.sso.yml up --build   # MOCKAN_DB_PORT=5433 if 5432 is taken
```

| What | Where |
| --- | --- |
| Panel (signs in through Keycloak) | `http://localhost:8081` → Keycloak login. Users (username = password): `admin` (a Mockan admin), `ehtesham`, `sara` |
| Keycloak | `http://localhost:8180` (`MOCKAN_KEYCLOAK_PORT`); console `admin` / `admin` |
| Redirect URIs registered | `http://localhost:{8081,5173,5174}/api/v1/auth/callback` |

The browser reaches Keycloak at `localhost:8180`, the Admin container at `keycloak:8080`. `KC_HOSTNAME` pins the issuer to the browser address and `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` lets the Admin use the container address for token and JWKS calls. To run the Admin on the host instead, use `MOCKAN_OIDC_ISSUER=http://localhost:8180/realms/internal`. The realm (`deploy/compose/keycloak/realm-internal.json`) and its secrets are for local use only; the users have fixed ids so the admin's `sub` is known (`00000000-0000-4000-8000-000000000001`).

**In shared environments**, the Panel signs developers in through the organization's Keycloak (AD behind it): OIDC authorization code + PKCE S256, no Mockan passwords. Nothing in the code is Keycloak-specific; it uses standard discovery. Decision: [`docs/agent/mockan-authentication.md`](../agent/mockan-authentication.md).

Ask DevOps for a **confidential OIDC client** and these four values:

| Value | Goes to | Notes |
| --- | --- | --- |
| Issuer URL | `MOCKAN_OIDC_ISSUER` | Normally `https://<keycloak-host>/realms/<realm>`. Mockan appends `/.well-known/openid-configuration`; the Admin must be able to reach it. |
| Client ID | `MOCKAN_OIDC_CLIENT_ID` | |
| Client secret | `MOCKAN_OIDC_CLIENT_SECRET` | Keep it in the secret store, never in Git. |
| Redirect URI | registered in Keycloak | **`https://<mockan-admin-host>/api/v1/auth/callback`** (the Panel's login is `GET /api/v1/auth/login`). |

Client settings: OpenID Connect, client authentication on (confidential), standard flow (authorization code) on, PKCE method `S256`, scopes `openid profile email`. Keep Keycloak's default `basic` client scope on the client: in Keycloak 25+ the `sub` claim of access tokens comes from it, and bearer validation requires `sub`.

Also set `MOCKAN_SESSION_SECRET` (≥ 32 random characters, the same on every Admin replica).

**The redirect URI is built from the request as the Admin sees it.** Behind the ingress, start uvicorn with `FORWARDED_ALLOW_IPS=<ingress CIDRs>` (the image already passes `--proxy-headers`; the uvicorn default trusts only `127.0.0.1`). Otherwise the Admin sees `http://` or the pod's host name and Keycloak answers `Invalid parameter: redirect_uri`.

**First admin.** Don't guess the `sub` (in Keycloak it is the user's UUID, not the email or username). Sign in once, read the Developer's `sso_subject` (`SELECT sso_subject, display_name FROM mockan.developers`), put it in `MOCKAN_ADMIN_SSO_SUBJECTS='["<sub>"]'` and restart the Admin; the next login is promoted to admin.

**Known limits** (accepted for now):
- **Logout** ends only the Mockan session, not the Keycloak SSO session, so signing in again may not ask for a password. RP-initiated logout is added only if it becomes a product requirement.
- **Bearer tokens** for Admin API clients need `aud` to contain `MOCKAN_OIDC_CLIENT_ID`. Keycloak access tokens default to `aud=account`; add an audience mapper (included client audience `mockan`, access token only) to the client before using bearer calls. The local realm already has one. This does not affect the Panel login.

**Real-login check (closes OQ-04):** the Admin starts; `GET /api/v1/auth/login` redirects to Keycloak; after AD sign-in the callback lands on the Panel with a session; `GET /api/v1/me` returns the Developer; the admin `sub` is configured.

## 4. Health and readiness (G-8)

| Endpoint | Answer |
| --- | --- |
| `GET /_mockan/health/live` | `200` while the process is up. |
| `GET /_mockan/health/ready` | `503 {"status":"starting"}` until the first snapshot loads; then `200 {"status":"ready"\|"degraded","snapshotAgeSeconds":n}`. **`degraded` stays in rotation:** the database is unreachable but the last good rules keep serving (PR-07). |

Use `ready` for the load balancer, and alert on `degraded` or a growing `snapshotAgeSeconds` (it should stay below `MOCKAN_SNAPSHOT_RELOAD_SECONDS` plus a few seconds).

## 4a. Metrics and tracing (PR-17)

Metrics are always collected in-process (OpenTelemetry SDK, no cost on the request path beyond a counter increment). Set `MOCKAN_OTEL_ENDPOINT` (an OTLP/HTTP collector, e.g. `http://collector:4318`) and both processes export them every `MOCKAN_OTEL_EXPORT_INTERVAL_SECONDS`.

| Metric | Type | Meaning / what to alert on |
| --- | --- | --- |
| `mockan_requests_total{source}` | counter | Gateway responses by `mock`, `proxy`, `error` (unknown slugs and Mockan problems are `error`; health checks and WebSockets aren't counted). A rising `error` share is `service_not_resolved`, `upstream_*` or `developer_not_found`: look at the logs. |
| `mockan_proxy_duration_ms` | histogram | Duration of proxied requests, Gateway overhead and the upstream included, streaming bodies timed to their end. |
| `mockan_snapshot_age_seconds` | gauge | Seconds since the rule snapshot was brought up to date. Should stay below `MOCKAN_SNAPSHOT_RELOAD_SECONDS` plus a few seconds; growing = the Gateway is `degraded`. Absent until the first snapshot loads. |
| `mockan_request_log_dropped_total` | counter | Request-log entries dropped (full queue or failed insert). Non-zero is not an outage (logging never slows requests) but the live view has gaps. |

**Tracing is opt-in** (`MOCKAN_TRACING_ENABLED=true`): the FastAPI and httpx instrumentation continue the caller's trace and the upstream then receives a **child** `traceparent` (same trace id, new span id) instead of the client's value unchanged; spans go to the same OTLP endpoint (health checks aren't traced). Off by default so that a request through Mockan is byte-identical to one sent directly (PR-03).

**Logs** are structured JSON with `developer`, `service`, `source` (`mock`/`proxy`/`error`), `rule_id` and, when tracing is on, `trace_id` wherever they are known at that point of the request.

## 5. Migrations

Alembic, schema `mockan` ([database.md §4](database.md#4-migrations)). Non-prod: `MOCKAN_MIGRATE_ON_STARTUP=true` on the Admin. Shared environments (`deploy.sh` does this, [§2a](#2a-deploying-from-ghcr-deploycomposedeploysh)): run `alembic upgrade head` as a job (the Admin image contains `alembic.ini` and `migrations/`) **before** rolling out new Gateways: old and new Gateways must both work with the new schema, so make migrations additive and remove columns in a later release.

## 6. Runbook

| Situation | What it means / what to do |
| --- | --- |
| **Readiness is `degraded`** | A Gateway can't reach PostgreSQL. It keeps serving its last good rules, so mocks and the proxy still work; edits made in the Admin won't arrive until the database is back. Check the database and the Gateway's `snapshot_reload_failed` logs. It recovers by itself (full reload on reconnect). |
| **A rule change takes longer than 2 s** | Check `snapshotAgeSeconds` on each Gateway. The LISTEN connection may have dropped: the service reconnects with backoff (≤ 30 s) and does a full reload; otherwise the 60 s periodic reload applies. Look for `snapshot_listening` / `snapshot_reconnecting` log lines. Restarting a Gateway is safe (it is stateless). |
| **A Developer was disabled or edited with plain SQL and the Gateways didn't notice** | A bulk `UPDATE` bypasses the ORM hook that sends `pg_notify`, so Gateways pick it up only at the next periodic reload (≤ 60 s). To make it immediate: `SELECT pg_notify('mockan_config_changed', '<developer-id>');` (use `catalog` after catalog edits). |
| **The live log lags or entries are missing** | The Gateway drops entries when its queue is full (`MOCKAN_REQUEST_LOG_QUEUE_SIZE`) or when a batch fails to insert (`request_log_write_failed` in its log). The Admin hub reconnects its LISTEN connection by itself (`request_log_hub_failed`). Missing history beyond 7 days / 5,000 rows is retention, not a bug. |
| **Users get `developer_not_found`** | Mistyped slug, a disabled Developer, or a Gateway that hasn't loaded the new Developer yet (≤ 2 s after claiming a slug). |
| **`service_not_resolved`** | No Service prefix matches the path, or the Service has no environment for the Developer's choice or default. Add the Service/environment (§7) or fix the default. |
| **`upstream_host_not_allowed` when saving** | The base URL's host isn't in `MOCKAN_ALLOWED_UPSTREAM_HOSTS`. Add the dev/stage host to the setting on **both** processes (the Gateway re-checks) and restart. |
| **Admin won't start** | In `oidc` mode it needs `MOCKAN_OIDC_*` and a 32+ character `MOCKAN_SESSION_SECRET`; the error names what is missing. |
| **Everyone is signed out after a deploy** | `MOCKAN_SESSION_SECRET` changed (or differs between replicas). |
| **Bearer calls get 401 `couldn't be verified`** | The Admin can't reach the provider's discovery/JWKS endpoint, or the token's audience isn't `MOCKAN_OIDC_CLIENT_ID` (Keycloak access tokens carry `aud=account` unless the client has an audience mapper; see [§3a](#3a-sign-in-with-keycloak-oq-04)). |

## 7. How to add a Service

As an admin, in the Panel's Services screen or through the API ([admin-api.md](admin-api.md)):

1. Make sure the upstream host is in `MOCKAN_ALLOWED_UPSTREAM_HOSTS` (both processes).
2. `POST /api/v1/services` with `name`, `pathPrefix` (e.g. `/limsa`), `stripPrefix` (does the upstream expect the prefix?), `rewriteOrigin` (does it reject foreign `Origin`s?) and `defaultEnvironment`.
3. `POST /api/v1/services/{id}/environments` for `dev` and/or `stage` with `baseUrl`, `timeoutSeconds` and `extraHeaders`. The default environment must have a base URL.
4. Within about 2 s every Gateway resolves `/{slug}/limsa/...` to it. Developers choose `dev` or `stage` per Service in the Panel.

## 8. Security posture

Reachable only from the internal network or VPN (ingress source ranges; NFR-05): not enforced by the application, **configure it at the ingress**. Dev auth mode must never run in a shared environment. Production hosts are never allowlisted. Secrets are masked in logs and in `audit_logs` (NFR-07); catalog `extraHeaders` are readable by every signed-in Developer, so don't put production secrets in them.
