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
| `admin_client` | function | `httpx.AsyncClient` against the Admin app (`tests/admin/conftest.py`; dev auth mode, test settings, the `session_factory` database). |
| `as_developer` | function | `await as_developer(slug, is_admin=False, is_enabled=True)` creates a Developer row and overrides `current_developer`, so every request acts as them; `as_developer.switch(developer)` changes who. |
| `audit_rows` | function | `await audit_rows()` returns every `audit_logs` row so far, oldest first. |
| `tests/admin/builders.py` | — | `rule_body(**overrides)`, `response_body(**overrides)`, `create_rule(client, **overrides)`, `update_body(rule)`: request bodies for the rule and response tests. |
| `listener` | function | Collects the `mockan_config_changed` payloads (`await listener.payloads(n)` / `listener.nothing()`); use it to assert a write notifies the right Developer id or `catalog`. |
| `fake_idp` | in `test_auth_oidc.py` | `tests/support/fake_idp.py`: a real OIDC provider on a live socket (discovery, JWKS, authorize, token) that signs ID tokens and bearer tokens with a generated RSA key. |

Rules:
- MUST NOT mock `httpx` in Gateway tests; use `fake_upstream` so streaming and headers are real.
- MUST NOT share DB state between tests: each Admin test runs in a transaction that is rolled back, or truncates tables in a fixture.
- No real OIDC provider in tests; override `current_developer`. The auth code itself (code flow, bearer validation) is tested against `fake_idp`, never mocked.
- Admin validation errors are asserted in the G-1 shape: `response.json()["errors"] == {"<field>": ["message"]}`.
- The Admin contract is pinned by `tests/admin/openapi.snapshot.json`; regenerate it with `UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/admin/test_openapi.py` and update `panel/src/api/types.ts` in the same change.

## 4. Minimum per PR

| Change | Required tests |
| --- | --- |
| Matching logic | Unit tests for the new/changed behaviour, including a precedence case. |
| Proxy transform / CORS | Gateway integration test against `fake_upstream`. |
| New Admin endpoint | Happy path, validation failure (422), other Developer's resource (404), non-admin on admin route (403). |
| Schema change | Migration applies on an empty DB (covered by `pg_container`), and model round-trip test. |
| Bug fix | A test that fails before the fix. |

## 5. Phase 1 acceptance tests

`server/tests/acceptance/` implements this table (plus PR-08 and PR-10) and the PRD §6 journey against a real Admin, a real Gateway and a real upstream on sockets, over one PostgreSQL; tests are named `test_pr_NN_…` and `test_traceability.py` fails if a Phase 1 id has none. What a single stack can't show (overhead benchmark, degraded mode, ingress restrictions, log masking, Phase 2 codes) is listed in the module docstring with where it is covered.

These map PRD Phase 1 checkboxes to tests and should exist before Phase 1 exit:

| PRD item | Test |
| --- | --- |
| PR-01 isolation | Developers A and B with rules on the same path; A's request only sees A's rule. |
| PR-02 proxy fidelity | Echo upstream receives identical method, path, query, headers (minus hop-by-hop) and body; 10 MB upload/download streamed. |
| PR-03 CORS/cookies/redirects | Preflight → 204 not forwarded; Origin echo; `Set-Cookie` Domain removed + Path prefixed; `Location` rewritten. |
| PR-04 routing | Longest prefix wins; `StripPrefix` true/false; env switch applies after notify. |
| PR-05 matching | All four match types, conditions, precedence order. |
| PR-06 static responses | Status, headers, content type, body, delay. |
| PR-07 hot reload | Rule saved via Admin → Gateway applies within 2 s (`tests/admin/test_admin_to_gateway.py`, two real apps on one PostgreSQL). |
| PR-09 source headers | `X-Mockan-Source` on mock, proxy, error and preflight responses; exposed via CORS. |
| PR-15 allowlist | Saving a non-allowlisted base URL → 422; Gateway refuses a non-allowlisted destination. |
| PR-16 errors | Each problem code with slug and path in the body. |
