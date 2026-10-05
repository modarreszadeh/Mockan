---
title: Mockan Backend — Tech stack
status: Draft (v0.1)
date: 2026-10-03
owner: Backend team
source: ../Agent/mockan-architecture.md (D-14 … D-18)
audience: Backend engineers and AI coding agents
---

# Mockan Backend — Tech stack

> **Summary:** every library the backend uses, the version range it is pinned to, and why it was picked. If you need a library that is not listed here, add it to this file in the same PR (C-01) and say why.

## 1. Runtime and tooling

| Concern | Choice | Pin (`server/pyproject.toml`) | Why |
| --- | --- | --- | --- |
| Language | CPython **3.14** | `requires-python = ">=3.14,<3.15"` | Current stable; stdlib `uuid.uuid7()`; all native deps ship cp314 wheels. |
| Package/env manager | **uv** | `uv.lock` committed | Fast, reproducible lockfile, manages the Python version (`.python-version`). |
| ASGI server | **Uvicorn** | `uvicorn[standard]>=0.54,<1` | `uvloop` + `httptools` for NFR-01; `--proxy-headers` replaces ASP.NET `UseForwardedHeaders`. |
| Lint + format | **ruff** | `ruff>=0.16` (dev) | One tool for lint, import sorting and formatting. |
| Type checking | **mypy** (strict) | `mypy>=2.4` (dev) | Catches contract drift between layers. |
| Layer rules | **import-linter** | `import-linter>=2.15` (dev) | Enforces architecture §14 rule 5 and the layer order. |

## 2. Application libraries

| Concern | Library | Pin | Notes |
| --- | --- | --- | --- |
| Web framework | `fastapi` | `>=0.142,<1` | Both apps. Gateway uses pure ASGI middleware for its pipeline. |
| Validation / models | `pydantic` | `>=2.13,<3` | Request/response models, domain-level validation in Admin. |
| Settings | `pydantic-settings` | `>=2.15,<3` | `MOCKAN_*` env vars, optional `.env`. |
| HTTP proxy client | `httpx` | `>=0.28,<1` | Shared `AsyncClient`, streaming both ways, `follow_redirects=False` (D-15). |
| WebSocket proxy client | `websockets` | `>=17,<18` | Upstream side of WebSocket bridging (D-15). |
| ORM | `sqlalchemy[asyncio]` | `>=2.1,<2.2` | Typed declarative models, async sessions (D-16). |
| PostgreSQL driver | `asyncpg` | `>=0.31,<1` | Used by SQLAlchemy and directly for `LISTEN` (D-07). |
| Migrations | `alembic` | `>=1.20,<2` | Autogenerate, then review by hand. |
| Regex | `google-re2` | `>=1.1,<2` | Linear-time regex (D-17). Import name: `re2`. |
| OIDC | `authlib` | `>=1.8,<2` | Code flow for the Panel session + JWT validation for bearer tokens (D-12). |
| JWT validation | `joserfc` | `>=1.7.5` | Bearer-token validation in `admin/oidc.py` (the library Authlib itself uses). Declared explicitly because we import it directly. |
| Sessions | Starlette `SessionMiddleware` (+ `itsdangerous`) | `itsdangerous>=2.2,<3` | Signed session cookie for the Panel. Pinned explicitly because Starlette only imports it lazily. |
| Logging | `structlog` | `>=26,<27` | JSON logs, masking processor (NFR-07). |
| Tracing / metrics | `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx` | `>=1.45` / `>=0.66b0` | Metric names in architecture §12.2 (`mockan.infrastructure.telemetry`). Each app owns its providers (nothing global), so tests read them with in-memory readers. Tracing is opt-in. |
| Templated bodies | `jinja2` (`SandboxedEnvironment`, `StrictUndefined`) | `>=3.1,<4` | PR-19 (B8c). Used by `mockan.matching.templating` only. |
| Fake data | `faker` | `>=40,<50` | PR-19 (B8c). Imported lazily on the first `fake.*` call; only a whitelist of generators is reachable from templates. |

> **Watch:** Authlib 1.8's `httpx` integration prefers the new `httpx2` package and warns (`AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead`) when it falls back to `httpx`. The fallback will be removed in a future Authlib release. The Admin uses it only for the OIDC token and JWKS calls. Adding `httpx2` would silence the warning and is a stack decision (D-15 names `httpx`); not done in B5.

## 3. Test libraries

| Library | Pin | Use |
| --- | --- | --- |
| `pytest` | `>=9.1` | Test runner. |
| `pytest-asyncio` | `>=1.4` | Async tests (`asyncio_mode = "auto"`). |
| `testcontainers[postgres]` | `>=4.15` | Real PostgreSQL for Admin and snapshot tests. Import from `testcontainers.community.postgres` (the old path is deprecated). |
| `pytest-cov` | `>=7` | Branch coverage gate on `mockan.matching` (B1 exit). |
| `httpx` (`ASGITransport`) | — | In-process calls to the FastAPI apps. |
| `uvicorn` (in-thread server) | — | Real fake upstream for streaming/SSE/WebSocket tests (no mocking of the network layer). |

## 4. Mapping from the v1.0 .NET design

Kept so readers of older notes or commits can translate. New code MUST use the right-hand column.

| v1.0 (.NET) | v1.1 (Python) | Decision |
| --- | --- | --- |
| ASP.NET Core on .NET 10 | FastAPI on Uvicorn, Python 3.14 | D-14 |
| YARP `IHttpForwarder`, `HttpTransformer` | `httpx.AsyncClient` streaming, `ProxyTransformer` | D-15 |
| EF Core + Npgsql, EF migrations | SQLAlchemy 2 async + asyncpg, Alembic | D-16 |
| EF `SaveChanges` interceptor | SQLAlchemy `before_commit` session event + `pg_notify` | D-07 / D-16 |
| `RegexOptions.NonBacktracking` + 50 ms timeout | RE2 (`google-re2`), ≤ 512-char patterns | D-17 |
| `Channel<T>` | `asyncio.Queue(maxsize=…)` | D-18 |
| SignalR hub | FastAPI WebSocket `/hubs/request-log` | D-18 |
| `TemplateMatcher` | Own template compiler in `mockan.matching` (`{name}`, `{*name}`) | arch §7.1 |
| Scriban / Bogus | Jinja2 sandbox / Faker | arch §7.3 |
| Serilog | structlog | arch §12.2 |
| `appsettings.json`, `Mockan:AllowedUpstreamHosts` | env vars via pydantic-settings, `MOCKAN_ALLOWED_UPSTREAM_HOSTS` | arch §12.3 |
| `Interlocked.Exchange` snapshot swap | single attribute assignment on `RuleSnapshotProvider` | arch §9 |
| xUnit, WebApplicationFactory, WireMock.Net | pytest, `httpx.ASGITransport`, in-thread Uvicorn fake upstream | [testing.md](testing.md) |
