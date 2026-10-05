---
title: Mockan Backend — Operations
status: Draft (v0.1, Phase 1)
date: 2026-10-04
owner: Backend team
related:
  - ../Agent/mockan-architecture.md
  - gateway.md
  - admin-api.md
  - database.md
audience: Engineers deploying and running Mockan, and AI coding agents
---

# Mockan Backend — Operations

> **Summary:** how to run the stack (compose and images), every `MOCKAN_*` setting, health and readiness, migrations, the runbook for the situations that will happen, and how to add a Service. Design context: [architecture §12](../Agent/mockan-architecture.md#12-security-operations-and-deployment).

## 1. Run it locally (compose)

```bash
cd deploy/compose
docker compose up --build                  # postgres + admin (with the Panel) + 2 gateways
docker compose --profile demo up --build   # ...plus a demo upstream (`fake-upstream:9000`)
MOCKAN_DB_PORT=55433 docker compose up -d  # when 5432 is taken
```

| What | Where |
| --- | --- |
| Panel + Admin API | `http://localhost:8081` (`MOCKAN_ADMIN_PORT` to change) |
| Gateway replicas | `http://localhost:8090`, `http://localhost:8091` (same database, own snapshot each: NFR-03) |
| PostgreSQL | `localhost:${MOCKAN_DB_PORT:-5432}`, user/password/db `mockan` |

The stack runs `MOCKAN_AUTH_MODE=dev` (no identity provider; G-9). The bare sign-in is `dev:dev`, which the compose file lists in `MOCKAN_ADMIN_SSO_SUBJECTS`, so it is an admin. **Never use dev mode in a shared environment.** The Admin applies the migrations on startup (`MOCKAN_MIGRATE_ON_STARTUP=true`); the Gateways wait for the Admin to be healthy.

The PRD §6 journey by hand (the `demo` profile registers nothing; do it through the Panel or the API):

```bash
A=http://localhost:8081; H='content-type: application/json'
curl -c jar -s "$A/api/v1/auth/login" -o /dev/null                       # sign in as dev:dev
curl -b jar -X PUT -H "$H" -d '{"slug":"ehtesham"}' $A/api/v1/me          # claim the slug
curl -b jar -X POST -H "$H" -d '{"name":"limsa","pathPrefix":"/limsa"}' $A/api/v1/services   # note its id
curl -b jar -X POST -H "$H" -d '{"environment":"stage","baseUrl":"http://fake-upstream:9000"}' $A/api/v1/services/<id>/environments
curl -i http://localhost:8090/ehtesham/limsa/api/v1/dashboard             # X-Mockan-Source: proxy
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

## 3. Settings

All are environment variables with the `MOCKAN_` prefix (`infrastructure/settings.py`, the only place that reads the environment; `server/.env.example` lists them). The table is arch §12.3.

| Variable | Used by | Default | Notes |
| --- | --- | --- | --- |
| `MOCKAN_DATABASE_URL` | both | `postgresql+asyncpg://mockan:mockan@localhost:5432/mockan` | |
| `MOCKAN_ALLOWED_UPSTREAM_HOSTS` | both | `[]` | JSON list; `*.x` matches subdomains only. Empty = nothing can be saved or proxied. **Never list production hosts** (NFR-06). |
| `MOCKAN_PUBLIC_BASE_URL` | both | `https://mock.novin-tools.com` | `Location` rewrite; returned as `publicBaseUrl` by `GET /me`. |
| `MOCKAN_DEFAULT_ALLOWED_ORIGINS` | both | `["http://localhost:*","http://127.0.0.1:*"]` | New Developers' `allowedOrigins`; Gateway fallback for unknown slugs. |
| `MOCKAN_LOG_LEVEL`, `MOCKAN_LOG_FORMAT` | both | `INFO`, `json` | `console` for local reading. |
| `MOCKAN_AUTH_MODE` | admin | `oidc` | `dev` = no identity provider, local only. |
| `MOCKAN_OIDC_ISSUER`, `_CLIENT_ID`, `_CLIENT_SECRET` | admin | empty | Required in `oidc` mode; the Admin **refuses to start** without them. `TODO(OQ-04)`. |
| `MOCKAN_SESSION_SECRET` | admin | empty | ≥ 32 random characters outside dev mode; same value on every Admin replica. |
| `MOCKAN_ADMIN_SSO_SUBJECTS` | admin | `[]` | Subjects that are admins (on creation and as a promotion at later logins; never demoted). |
| `MOCKAN_MIGRATE_ON_STARTUP` | admin | `false` | Non-prod only. |
| `MOCKAN_PANEL_BASE_PATH` | admin | `/` | Where the built Panel is served. `TODO(OQ-03)`. |
| `MOCKAN_SNAPSHOT_RELOAD_SECONDS` | gateway | `60` | Safety-net full reload. |
| `MOCKAN_SNAPSHOT_DEBOUNCE_MS` | gateway | `200` | Coalesces notifications. |

## 4. Health and readiness (G-8)

| Endpoint | Answer |
| --- | --- |
| `GET /_mockan/health/live` | `200` while the process is up. |
| `GET /_mockan/health/ready` | `503 {"status":"starting"}` until the first snapshot loads; then `200 {"status":"ready"\|"degraded","snapshotAgeSeconds":n}`. **`degraded` stays in rotation:** the database is unreachable but the last good rules keep serving (PR-07). |

Use `ready` for the load balancer, and alert on `degraded` or a growing `snapshotAgeSeconds` (it should stay below `MOCKAN_SNAPSHOT_RELOAD_SECONDS` plus a few seconds).

## 5. Migrations

Alembic, schema `mockan` ([database.md §4](database.md#4-migrations)). Non-prod: `MOCKAN_MIGRATE_ON_STARTUP=true` on the Admin. Shared environments: run `alembic upgrade head` as a job (the Admin image contains `alembic.ini` and `migrations/`) **before** rolling out new Gateways: old and new Gateways must both work with the new schema, so make migrations additive and remove columns in a later release.

## 6. Runbook

| Situation | What it means / what to do |
| --- | --- |
| **Readiness is `degraded`** | A Gateway can't reach PostgreSQL. It keeps serving its last good rules, so mocks and the proxy still work; edits made in the Admin won't arrive until the database is back. Check the database and the Gateway's `snapshot_reload_failed` logs. It recovers by itself (full reload on reconnect). |
| **A rule change takes longer than 2 s** | Check `snapshotAgeSeconds` on each Gateway. The LISTEN connection may have dropped: the service reconnects with backoff (≤ 30 s) and does a full reload; otherwise the 60 s periodic reload applies. Look for `snapshot_listening` / `snapshot_reconnecting` log lines. Restarting a Gateway is safe (it is stateless). |
| **A Developer was disabled or edited with plain SQL and the Gateways didn't notice** | A bulk `UPDATE` bypasses the ORM hook that sends `pg_notify`, so Gateways pick it up only at the next periodic reload (≤ 60 s). To make it immediate: `SELECT pg_notify('mockan_config_changed', '<developer-id>');` (use `catalog` after catalog edits). |
| **Users get `developer_not_found`** | Mistyped slug, a disabled Developer, or a Gateway that hasn't loaded the new Developer yet (≤ 2 s after claiming a slug). |
| **`service_not_resolved`** | No Service prefix matches the path, or the Service has no environment for the Developer's choice or default. Add the Service/environment (§7) or fix the default. |
| **`upstream_host_not_allowed` when saving** | The base URL's host isn't in `MOCKAN_ALLOWED_UPSTREAM_HOSTS`. Add the dev/stage host to the setting on **both** processes (the Gateway re-checks) and restart. |
| **Admin won't start** | In `oidc` mode it needs `MOCKAN_OIDC_*` and a 32+ character `MOCKAN_SESSION_SECRET`; the error names what is missing. |
| **Everyone is signed out after a deploy** | `MOCKAN_SESSION_SECRET` changed (or differs between replicas). |
| **Bearer calls get 401 `couldn't be verified`** | The Admin can't reach the provider's discovery/JWKS endpoint, or the token's audience isn't `MOCKAN_OIDC_CLIENT_ID` (`TODO(OQ-04)`). |

## 7. How to add a Service

As an admin, in the Panel's Services screen or through the API ([admin-api.md](admin-api.md)):

1. Make sure the upstream host is in `MOCKAN_ALLOWED_UPSTREAM_HOSTS` (both processes).
2. `POST /api/v1/services` with `name`, `pathPrefix` (e.g. `/limsa`), `stripPrefix` (does the upstream expect the prefix?), `rewriteOrigin` (does it reject foreign `Origin`s?) and `defaultEnvironment`.
3. `POST /api/v1/services/{id}/environments` for `dev` and/or `stage` with `baseUrl`, `timeoutSeconds` and `extraHeaders`. The default environment must have a base URL.
4. Within about 2 s every Gateway resolves `/{slug}/limsa/...` to it. Developers choose `dev` or `stage` per Service in the Panel.

## 8. Security posture

Reachable only from the internal network or VPN (ingress source ranges; NFR-05): not enforced by the application, **configure it at the ingress**. Dev auth mode must never run in a shared environment. Production hosts are never allowlisted. Secrets are masked in logs and in `audit_logs` (NFR-07); catalog `extraHeaders` are readable by every signed-in Developer, so don't put production secrets in them.
