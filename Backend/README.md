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

## Documents

| File | Topic | Status |
| --- | --- | --- |
| [tech-stack.md](tech-stack.md) | Libraries, versions, and why each was chosen; .NET → Python mapping from v1.0. | Draft |
| [project-structure.md](project-structure.md) | Folder layout, module boundaries, import rules, entry points, commands. | Draft |
| [conventions.md](conventions.md) | Code style, naming, async rules, errors, logging, config. | Draft |
| [testing.md](testing.md) | Test layers, tools, fixtures, naming, what must be tested. | Draft |

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
docker compose -f ../deploy/compose/docker-compose.yml up -d postgres
uv run alembic upgrade head                    # apply migrations
uv run uvicorn mockan.admin.app:create_app --factory --port 8081 --reload
uv run uvicorn mockan.gateway.app:create_app --factory --port 8080 --reload
uv run pytest                                  # all tests
```
