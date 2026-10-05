---
title: Mockan Backend — Code conventions
status: Draft (v0.1)
date: 2026-10-03
owner: Backend team
related:
  - ../agent/mockan-architecture.md
  - project-structure.md
audience: Backend engineers and AI coding agents
---

# Mockan Backend — Code conventions

> **Summary:** the rules backend code in `server/` follows. CI enforces what it can (ruff, mypy, import-linter); reviewers enforce the rest. Architecture §14 rules always win over this file.

## 1. Formatting and typing

- MUST pass `ruff check` and `ruff format` (line length 100, rule sets `E,F,W,I,B,UP,SIM,ASYNC,RUF`).
- MUST pass `mypy --strict` on `src/`. No bare `Any` in public signatures; `# type: ignore[...]` needs the error code and a reason.
- Use modern syntax: `X | None`, `list[str]`, `type` aliases, `match` where it reads better.
- Every module starts with a one-line docstring saying what it is for.

## 2. Naming

| Thing | Style | Example |
| --- | --- | --- |
| Glossary concepts (arch §2) | exact glossary word, PascalCase class | `Developer`, `MockRule`, `MockResponse`, `ServiceEnvironment` |
| Modules, functions, variables | snake_case | `mock_rule.py`, `resolve_service()` |
| Constants | UPPER_SNAKE | `RESERVED_SLUGS`, `MAX_DELAY_MS` |
| DB tables / columns | snake_case, plural tables | `mock_rules.active_response_id` |
| JSON fields in Admin API | camelCase via Pydantic alias | `activeResponseId`, `allowedOrigins` |
| Enum values | PascalCase strings matching arch | `MatchType.EXACT = "Exact"`, `RequestSource.PROXIED = "Proxied"` |
| Problem codes | snake_case, stable | `developer_not_found` |

MUST NOT use the word `tenant` anywhere (D-01).

## 3. Async rules

- All I/O is async (`httpx.AsyncClient`, SQLAlchemy `AsyncSession`, asyncpg). No `requests`, no sync DB drivers.
- MUST NOT call `time.sleep`, blocking file I/O or CPU-heavy work on the Gateway request path. Use `asyncio.sleep` for mock delays.
- Background tasks (snapshot service, request-log writer) are started and stopped in the FastAPI `lifespan`, never with bare `asyncio.create_task` at import time. Keep a reference to each task and cancel it on shutdown.
- One shared `httpx.AsyncClient` per Gateway process, created in `lifespan` and stored on `app.state`.

## 4. Gateway specifics

- Pipeline steps are pure ASGI middleware; MUST NOT use `BaseHTTPMiddleware` or `@app.middleware("http")` (they break streaming).
- MUST NOT read whole bodies (`await request.body()`, `response.aread()`) on the proxy path (arch §14 rule 3).
- Read `RuleSnapshotProvider.current` once at the start of a request and use that object for the whole request.
- Every response path (mock, proxy, error, preflight) sets `X-Mockan-Source`.

## 5. Admin specifics

- Routers are thin: parse input (Pydantic), call a function in `admin/services/`, return a schema. Business rules and audit writes live in `admin/services/`.
- Every `/me/*` handler depends on `current_developer` and filters every query by `developer_id`. Never accept a `developerId` from the client for `/me/*` routes.
- Catalog writes depend on `require_admin`.
- Each write that changes config also writes an `audit_logs` row in the same transaction.
- Inputs use `extra="forbid"`, so a client can't set a field it shouldn't (`isAdmin`, `developerId`). Writes require `Content-Type: application/json`, and the session cookie is `HttpOnly; SameSite=Lax` (`Secure` outside dev mode); a cross-site form can send neither, so there is no CSRF token (G-12). The Admin sets no CORS headers.
- A resource that doesn't exist or belongs to someone else is `404 not_found`, never `403`.
- Details: [admin-api.md](admin-api.md).

## 6. Errors

- Mockan-generated errors are RFC 7807 `application/problem+json`:

```json
{
  "type": "https://mock.novin-tools.com/problems/developer_not_found",
  "title": "Developer not found",
  "status": 404,
  "code": "developer_not_found",
  "detail": "No enabled Developer with slug 'ehtesam'.",
  "developer": "ehtesam",
  "path": "/limsa/api/v1/dashboard"
}
```

- Codes come from `mockan.domain.errors.ErrorCode`; never invent a code inline.
- Admin validation errors use status `422` with `code = "validation_failed"` and an `errors` **map** `{"<camelCase.dotted.path>": ["message", …]}` (G-1: the shape the Panel maps onto form fields; it replaces the earlier `{field, message}` list). Services raise `DomainError(code, status, title, detail, errors)`; `admin/problems.py` renders it.
- Don't catch broad `Exception` except at the outermost layer that turns it into a problem response and logs it.

## 7. Logging and secrets

- Use `structlog.get_logger()`; log events as short snake_case names with key/value context: `log.info("snapshot_reloaded", developers=12, duration_ms=8)`.
- Bind `developer`, `service`, `source`, `rule_id`, `trace_id` on Gateway logs.
- MUST NOT log raw headers or bodies; pass them through `mockan.infrastructure.masking` first (NFR-07).

## 8. Configuration

- All settings live in `MockanSettings` (`mockan/infrastructure/settings.py`), env prefix `MOCKAN_`. No `os.environ` reads elsewhere.
- A new setting MUST be added to the table in arch §12.3 in the same PR.

## 9. Open questions and decisions in code

- Code that depends on an open question uses the stated default and a marker: `# TODO(OQ-02): assumes bearer tokens; revisit if apps use cookies.`
- Reference decisions where they drive non-obvious code: `# D-17: RE2 is linear-time, so no per-match timeout.`
- Commit messages and PR descriptions reference `FR-`/`NFR-`/`D-`/`PR-` IDs they implement.
