---
title: Mockan Backend — Testing strategy
status: Draft (v0.1)
date: 2026-10-03
owner: Backend team
related:
  - ../Agent/mockan-architecture.md
  - project-structure.md
audience: Backend engineers and AI coding agents
---

# Mockan Backend — Testing strategy

> **Summary:** which tests exist, what each layer proves, the tools and fixtures to use, and the minimum a PR must add. Architecture §14 rule 6 requires tests for every matching or transform change.

## 1. Test layers

| Layer | Folder | Proves | Tools | Needs Docker |
| --- | --- | --- | --- | --- |
| Matching unit | `server/tests/matching/` | Every match type, condition and precedence rule (arch §7); service resolution (longest prefix, env choice). | pytest, plain objects | No |
| Gateway integration | `server/tests/gateway/` | Pipeline order, CORS, mock responses, proxy transforms (arch §6.3), streaming, SSE, WebSocket, error codes. | pytest-asyncio, `httpx.AsyncClient(transport=ASGITransport(app))` or a real Uvicorn server, in-thread fake upstream | No (snapshot built in memory) |
| Admin API | `server/tests/admin/` | Endpoints, validation rules (arch §10), authorisation (own workspace only, admin-only catalog), audit rows, `pg_notify` emission. | pytest-asyncio, Testcontainers PostgreSQL, Alembic migrations applied once per session | Yes |
| Snapshot / LISTEN | `server/tests/gateway/test_snapshot_service.py` | Change notification reaches the Gateway and the new rule applies within 2 s (FR-08); DB down → keeps last snapshot, `ready = degraded`. | Testcontainers PostgreSQL | Yes |

Precedence is checked against the Panel with one shared fixture, `server/tests/matching/precedence_parity.json`, run by `test_precedence_parity.py` and `panel/src/lib/precedence.parity.test.ts`; change both sides together.

Tests that need Docker are marked `@pytest.mark.db`; run fast tests only with `uv run pytest -m "not db"`.

## 2. Naming and traceability

- File per unit under test: `test_matcher.py`, `test_transform.py`, `test_rules_api.py`.
- Test names say the behaviour: `test_exact_match_ignores_trailing_slash`.
- Reference requirement IDs with a marker so coverage per requirement can be listed:

```python
@pytest.mark.req("FR-05")
def test_template_rule_matches_single_segment() -> None: ...
```

  (`req` is registered in `pyproject.toml`; `uv run pytest -m req --collect-only -q` lists them.)

## 3. Fixtures and fakes

| Fixture | Scope | What it gives |
| --- | --- | --- |
| `snapshot_builder` | function | Fluent helper (`tests/support/snapshot_builder.py`) to build a `RuleSnapshot` in memory (developers, services, rules) without a DB. |
| `fake_upstream` | session (state reset per test) | A real Uvicorn server on a random port running a small Starlette app (`tests/support/fake_upstream.py`): `/echo` (method, raw path, raw query, headers, body length and SHA-256), `/stream`, `/sse`, `/download?mb=`, `/truncated`, `/slow`, `/redirect`, `/redirect-root`, `/created`, `/set-cookie`, `/cors`, `/response-headers`, `/gzip`, `/status/{code}`, and WebSockets `/ws`, `/ws/headers`, `/ws/proto`, `/ws/deny`. Its host is added to the allowlist in test settings. |
| `live_gateway` | function | The Gateway on its own real Uvicorn socket over a swappable in-memory snapshot, plus an `httpx` client and the `RuleSnapshotProvider`. Use it when a test needs real streaming, SSE or WebSockets: `ASGITransport` buffers whole responses. |
| `gateway_client` | function | `httpx.AsyncClient` against the Gateway app with a provided snapshot (in-process; runs the app lifespan on first use). |
| `pg_container` | session | Testcontainers PostgreSQL 18 with migrations applied. |
| `admin_client` | function | `httpx.AsyncClient` against the Admin app; auth is replaced by a test dependency override that logs in as a given Developer (`as_developer(slug, is_admin=False)`). |

Rules:
- MUST NOT mock `httpx` in Gateway tests; use `fake_upstream` so streaming and headers are real.
- MUST NOT share DB state between tests: each Admin test runs in a transaction that is rolled back, or truncates tables in a fixture.
- No real OIDC provider in tests; override `current_developer`.

## 4. Minimum per PR

| Change | Required tests |
| --- | --- |
| Matching logic | Unit tests for the new/changed behaviour, including a precedence case. |
| Proxy transform / CORS | Gateway integration test against `fake_upstream`. |
| New Admin endpoint | Happy path, validation failure (422), other Developer's resource (404), non-admin on admin route (403). |
| Schema change | Migration applies on an empty DB (covered by `pg_container`), and model round-trip test. |
| Bug fix | A test that fails before the fix. |

## 5. Phase 1 acceptance tests

These map PRD Phase 1 checkboxes to tests and should exist before Phase 1 exit:

| PRD item | Test |
| --- | --- |
| PR-01 isolation | Developers A and B with rules on the same path; A's request only sees A's rule. |
| PR-02 proxy fidelity | Echo upstream receives identical method, path, query, headers (minus hop-by-hop) and body; 10 MB upload/download streamed. |
| PR-03 CORS/cookies/redirects | Preflight → 204 not forwarded; Origin echo; `Set-Cookie` Domain removed + Path prefixed; `Location` rewritten. |
| PR-04 routing | Longest prefix wins; `StripPrefix` true/false; env switch applies after notify. |
| PR-05 matching | All four match types, conditions, precedence order. |
| PR-06 static responses | Status, headers, content type, body, delay. |
| PR-07 hot reload | Rule saved via Admin → Gateway applies within 2 s. |
| PR-09 source headers | `X-Mockan-Source` on mock, proxy, error and preflight responses; exposed via CORS. |
| PR-15 allowlist | Saving a non-allowlisted base URL → 422; Gateway refuses a non-allowlisted destination. |
| PR-16 errors | Each problem code with slug and path in the body. |
