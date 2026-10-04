---
title: Mockan Backend — Documentation index
status: Draft (v0.1)
date: 2026-10-03
owner: Backend team
related:
  - ../Agent/mockan-architecture.md
  - ../Product/mockan-prd.md
audience: Backend engineers and AI coding agents working in `server/`
---

# Mockan Backend — Documentation index

> **What this folder covers:** how the Mockan backend (Gateway + Admin API) is built in Python/FastAPI: the stack, folder layout, code conventions and testing. **What** the system does and **why** is in the [PRD](../Product/mockan-prd.md); the system-level **how** (pipeline, matching, data model, Admin API) is in the [architecture](../Agent/mockan-architecture.md). This folder does not repeat those; it links to them.

## Quick facts

| Item | Value |
| --- | --- |
| Language / runtime | Python 3.14 (D-14) |
| Web framework | FastAPI on Uvicorn (`uvloop`, `httptools`) |
| Code location | `server/` (one uv project, one package `mockan`) |
| Processes | `mockan.gateway` (data plane), `mockan.admin` (control plane) — D-05 |
| Database | PostgreSQL via SQLAlchemy 2 async + asyncpg; migrations with Alembic (D-16) |
| Proxy | `httpx.AsyncClient` streaming + `websockets` bridge (D-15) |
| Regex engine | RE2 via `google-re2` (D-17) |
| Phase | In progress: B0 (skeleton), B1 (domain + matching), B2 (infrastructure), B3 (Gateway core), B4 (proxy) and B5 (Admin API foundation) done. Build order in [implementation-plan.md](implementation-plan.md) (B0 → B7 = Phase 1). |

## Documents

| File | Topic | Status |
| --- | --- | --- |
| [implementation-plan.md](implementation-plan.md) | Milestones B0–B8 to prepare and build `server/`; gaps settled between PRD, architecture and the Panel contract; backend open questions (OQ-Bx). | Draft |
| [tech-stack.md](tech-stack.md) | Libraries, versions, and why each was chosen; .NET → Python mapping from v1.0. | Draft |
| [project-structure.md](project-structure.md) | Folder layout, module boundaries, import rules, entry points, commands. | Draft |
| [conventions.md](conventions.md) | Code style, naming, async rules, errors, logging, config. | Draft |
| [testing.md](testing.md) | Test layers, tools, fixtures, naming, what must be tested. | Draft |
| [admin-api.md](admin-api.md) | Admin API: auth (OIDC, dev mode), routes, payloads and limits, error codes, decisions, serving the Panel. | Draft |
| [gateway.md](gateway.md) | Gateway pipeline, CORS, mock responses, proxy and WebSocket bridge, snapshot service, health, problem codes, performance. | Draft |
| [database.md](database.md) | Schema conventions, FK delete policy, change notification, migration rules. | Draft |

Covered in the architecture doc for now (split into this folder when they grow):

| Topic | Where |
| --- | --- |
| Gateway pipeline and proxy transforms | [architecture §6](../Agent/mockan-architecture.md#6-request-lifecycle-gateway) |
| Matching engine and precedence | [architecture §7](../Agent/mockan-architecture.md#7-mock-matching) |
| Database schema and change notification | [architecture §8](../Agent/mockan-architecture.md#8-data-model) |
| Admin API contract and validation | [architecture §10](../Agent/mockan-architecture.md#10-admin-api-control-plane) (live OpenAPI at `/api/v1/openapi.json`) |
| Configuration variables | [architecture §12.3](../Agent/mockan-architecture.md#123-deployment) |

## Quick start (local)

```bash
cd server
uv sync                                        # create .venv, install deps from uv.lock
docker compose -f ../deploy/compose/docker-compose.yml up -d postgres   # MOCKAN_DB_PORT=5433 if 5432 is taken
uv run alembic upgrade head                    # apply migrations
uv run uvicorn mockan.admin.app:create_app --factory --port 8081 --reload
uv run uvicorn mockan.gateway.app:create_app --factory --port 8080 --reload
uv run pytest                                  # all tests (db tests need Docker; -m "not db" skips them)
./scripts/check.sh                             # lint + format + mypy + import contracts + tests (the `check` command)
```
