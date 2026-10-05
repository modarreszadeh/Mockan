"""Phase 1 acceptance, one test per PRD requirement (PR-01 ... PR-16), named by its id.

Each test drives the real Admin and Gateway over HTTP (see `conftest.py`) and asserts the
checkboxes of the requirement in `Product/mockan-prd.md` §7.1. Deeper edge cases live in the unit
and integration suites; these prove the requirement end to end.

Covered elsewhere because they need something this stack doesn't have:
- PR-02 overhead <= 10 ms p95: `server/bench/proxy_overhead.py` (manual, NFR-01).
- PR-07 "database unreachable -> keep serving, `degraded`": `tests/gateway/test_snapshot_service.py`
  (it stops its own PostgreSQL container).
- PR-15 "reachable only from the internal network": ingress configuration (operations.md).
- PR-15 log masking: `tests/infrastructure/test_masking.py`.
- PR-16 `mock_render_failed`: Phase 2 (B8c).
- PR-18 (the Panel): `panel/` tests.
"""

import hashlib
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from mockan.infrastructure.db.models import AuditLog, Developer
from tests.acceptance.conftest import (
    PUBLIC_BASE_URL,
    TWO_SECONDS,
    Person,
    Stack,
    Upstream,
    eventually,
)
from tests.admin.builders import response_body
from tests.support.fake_upstream import download_sha256

pytestmark = pytest.mark.db

LOCALHOST = "http://localhost:5173"


def echoed(response: httpx.Response) -> dict[str, Any]:
    """The fake upstream's `/echo` answer, with its headers as a lower-cased dict."""
    body: dict[str, Any] = response.json()
    body["headerMap"] = {name.lower(): value for name, value in body["headers"]}
    return body


async def dev(stack: Stack, name: str = "ehtesham") -> Person:
    return await stack.sign_in(name, slug=name)


# ---- PR-01 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-01")
async def test_pr_01_workspaces_are_isolated(stack: Stack, root: Person) -> None:
    alice, bob = await dev(stack, "alice"), await dev(stack, "bob")

    # Slug rules: reserved and taken slugs are rejected with a clear message.
    newcomer = await stack.sign_in("carol")
    assert (await newcomer.api.get("/api/v1/me")).json()["slug"] is None
    for reserved in ("_mockan", "api", "hubs", "health"):
        rejected = await newcomer.api.put("/api/v1/me", json={"slug": reserved})
        assert rejected.status_code == 422, reserved
        assert rejected.json()["errors"]["slug"]
    taken = await newcomer.api.put("/api/v1/me", json={"slug": "alice"})
    assert (taken.status_code, taken.json()["code"]) == (409, "slug_taken")
    badly_formed = await newcomer.api.put("/api/v1/me", json={"slug": "Carol 1"})
    assert badly_formed.status_code == 422
    await newcomer.claim("carol")

    # Same path, different rules: each only sees their own.
    await alice.rule(responses=[response_body(body='{"who":"alice"}')])
    await bob.rule(responses=[response_body(body='{"who":"bob"}')])
    await alice.becomes("/echo/mocked", source="mock")
    await bob.becomes("/echo/mocked", source="mock")
    assert (await alice.get("/echo/mocked")).json() == {"who": "alice"}
    assert (await bob.get("/echo/mocked")).json() == {"who": "bob"}
    assert (await newcomer.get("/echo/mocked")).headers["x-mockan-source"] == "proxy"

    # A disabled Developer's address is a 404 developer_not_found; so is an unknown one.
    async with stack.session_factory() as session:  # an ORM write, so NOTIFY fires (operations.md)
        bob_row = await session.scalar(select(Developer).where(Developer.slug == "bob"))
        assert bob_row is not None
        bob_row.is_enabled = False
        await session.commit()

    async def disabled() -> bool:
        return (await bob.get("/echo/mocked")).status_code == 404

    await eventually(disabled, what="bob's address to be 404")
    gone = await bob.get("/echo/mocked")
    assert gone.json()["code"] == "developer_not_found"
    unknown = await stack.gateway_client.get("/nobody/echo/mocked")
    assert (unknown.status_code, unknown.json()["code"]) == (404, "developer_not_found")
    assert (await alice.get("/echo/mocked")).json() == {"who": "alice"}  # alice is unaffected


# ---- PR-02 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-02")
async def test_pr_02_unmatched_requests_are_proxied_unchanged_and_large_bodies_stream(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    body = b"payload-\x00\xff-bytes"

    via_mockan = await person.call(
        "POST",
        "/echo/a/B/c?x=1&y=%20z&x=2",
        headers={"x-custom": "abc", "content-type": "application/octet-stream"},
        content=body,
    )
    direct = await httpx.AsyncClient(trust_env=False).post(
        f"{stack.upstream.url}/echo/a/B/c?x=1&y=%20z&x=2",
        headers={"x-custom": "abc", "content-type": "application/octet-stream"},
        content=body,
    )

    got, want = echoed(via_mockan), echoed(direct)
    assert via_mockan.headers["x-mockan-source"] == "proxy"
    for field in ("method", "rawPath", "query", "bodyLength", "bodySha256", "body"):
        assert got[field] == want[field], field
    assert got["rawPath"] == "/echo/a/B/c"
    assert got["headerMap"]["x-custom"] == "abc"
    assert got["headerMap"]["content-type"] == "application/octet-stream"

    # 10 MB each way, streamed (bounded memory is asserted in tests/gateway/test_proxy.py).
    download = await person.get("/download", params={"mb": 10})
    assert len(download.content) == 10 * 1024 * 1024
    assert hashlib.sha256(download.content).hexdigest() == download_sha256(10)

    async def upload() -> AsyncIterator[bytes]:
        for _ in range(160):
            yield b"u" * 65536

    uploaded = await person.call("POST", "/echo", content=upload())
    assert echoed(uploaded)["bodyLength"] == 160 * 65536
    assert echoed(uploaded)["bodySha256"] == hashlib.sha256(b"u" * 65536 * 160).hexdigest()

    # SSE arrives while the stream is still open.
    async with person.stack.gateway_client.stream("GET", f"/{person.slug}/stream") as response:
        first = await response.aiter_raw().__anext__()
    assert first.startswith(b"chunk-0|")


# ---- PR-03 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-03")
async def test_pr_03_browsers_can_read_proxied_and_mocked_responses(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    origin = {"origin": LOCALHOST}

    # Preflight: answered by Mockan, never forwarded.
    preflight = await person.call(
        "OPTIONS",
        "/echo",
        headers={
            **origin,
            "access-control-request-method": "POST",
            "access-control-request-headers": "x-a",
        },
    )
    assert preflight.status_code == 204
    assert preflight.content == b""  # the upstream would have answered with its echo JSON
    assert preflight.headers["access-control-allow-origin"] == LOCALHOST
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert preflight.headers["access-control-max-age"] == "600"

    # Origin echo only for allowed origins; upstream CORS headers are replaced.
    proxied = await person.get("/cors", headers=origin)
    assert proxied.headers["access-control-allow-origin"] == LOCALHOST
    assert "evil.example" not in str(proxied.headers)
    assert "x-secret" not in proxied.headers["access-control-expose-headers"].lower()
    assert proxied.headers["x-keep"] == "yes"
    assert (
        "access-control-allow-origin"
        not in (await person.get("/echo", headers={"origin": "https://evil.example"})).headers
    )

    # Location points back at Mockan; Set-Cookie loses Domain and gets a slug-prefixed Path.
    redirect = await person.get("/redirect")
    assert redirect.status_code == 302
    assert redirect.headers["location"] == f"{PUBLIC_BASE_URL}/ehtesham/echo?via=redirect"
    cookies = (await person.get("/set-cookie")).headers.get_list("set-cookie")
    assert any("Path=/ehtesham/x" in c and "Domain" not in c for c in cookies)
    assert any(c.startswith("b=2") and "Path=/ehtesham" in c for c in cookies)

    # Identity headers reach the upstream; traceparent is forwarded.
    trace = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    seen = echoed(await person.get("/echo", headers={"traceparent": trace}))["headerMap"]
    assert seen["x-mockan-developer"] == "ehtesham"
    assert seen["x-forwarded-prefix"] == "/ehtesham"
    assert seen["traceparent"] == trace

    # A mocked response is readable too.
    await person.rule()
    await person.becomes("/echo/mocked", source="mock")
    mocked = await person.get("/echo/mocked", headers=origin)
    assert mocked.headers["access-control-allow-origin"] == LOCALHOST

    # The Developer edits their AllowedOrigins in the Panel; the Gateway follows within 2 s.
    await person.put("/me", {"allowedOrigins": ["https://app.example"]})

    async def origins_changed() -> bool:
        return (
            "access-control-allow-origin" not in (await person.get("/echo", headers=origin)).headers
        )

    await eventually(origins_changed, what="the AllowedOrigins change")
    allowed = await person.get("/echo", headers={"origin": "https://app.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://app.example"


# ---- PR-04 ---------------------------------------------------------------------------------


def served_by(response: httpx.Response) -> str:
    """The port of the upstream that answered (the echo reports the `Host` it was called with)."""
    if response.status_code != 200:  # e.g. while a catalog change is still being applied
        return ""
    return echoed(response)["headerMap"]["host"].rsplit(":", 1)[1]


@pytest.mark.req("PR-04")
async def test_pr_04_services_resolve_by_longest_prefix_and_environments_can_be_chosen(
    stack: Stack, root: Person, start_upstream: Callable[[], Upstream]
) -> None:
    person = await dev(stack)
    other = start_upstream()
    main_port, other_port = str(stack.upstream.server.port), str(other.server.port)

    async def on_port(path: str, port: str) -> bool:
        return served_by(await person.get(path)) == port

    # Longest prefix wins: `/echo/orders` (the other upstream) beats `/echo` (the main one).
    await stack.add_service(root, "orders", prefix="/echo/orders", stage=other.url)

    async def orders_resolved() -> bool:
        return await on_port("/echo/orders/1", other_port)

    await eventually(orders_resolved, what="the new Service")
    assert await on_port("/echo/elsewhere", main_port)

    # StripPrefix per Service: `/api` is stripped before the upstream sees the path.
    await stack.add_service(root, "api", prefix="/api", strip_prefix=True)

    async def stripped() -> bool:
        response = await person.get("/api/echo/x?q=1")
        return response.status_code == 200 and echoed(response)["rawPath"] == "/echo/x"

    await eventually(stripped, what="the stripped Service")
    kept = await person.get("/echo/x")  # `/echo` keeps its prefix
    assert (kept.status_code, echoed(kept)["rawPath"]) == (200, "/echo/x")

    # Environment: the Service default is stage; the Developer picks dev; applied within 2 s.
    service = await stack.add_service(
        root, "switchable", prefix="/echo/env", stage=stack.upstream.url, dev=other.url
    )
    listed = (await root.api.get("/api/v1/services")).json()
    environments = {
        e["environment"]: e["id"]
        for s in listed
        if s["id"] == service["id"]
        for e in s["environments"]
    }

    async def env_resolved() -> bool:
        return await on_port("/echo/env/x", main_port)

    await eventually(env_resolved, what="the switchable Service")  # default environment: stage
    await person.put(
        "/me/service-settings",
        [{"serviceId": service["id"], "serviceEnvironmentId": environments["dev"]}],
    )

    async def on_dev() -> bool:
        return served_by(await person.get("/echo/env/x")) == other_port

    async def on_stage() -> bool:
        return served_by(await person.get("/echo/env/x")) == main_port

    await eventually(on_dev, what="the switch to dev")
    await person.put("/me/service-settings", [])  # back to the default
    await eventually(on_stage, what="the switch back to stage")


# ---- PR-05 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-05")
async def test_pr_05_rules_match_by_type_method_conditions_and_precedence(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)

    def body(name: str) -> list[dict[str, Any]]:
        return [response_body(body=json.dumps({"rule": name}))]

    async def served(path: str, **kwargs: Any) -> str | None:
        response = await person.get(path, **kwargs)
        return response.json()["rule"] if response.headers["x-mockan-source"] == "mock" else None

    # Match types. Exact ignores case and a trailing slash; the others as documented.
    await person.rule(name="exact", pattern="/echo/Orders", responses=body("exact"))
    await person.rule(
        name="template",
        matchType="Template",
        pattern="/echo/items/{id}",
        responses=body("template"),
    )
    await person.rule(
        name="rest", matchType="Template", pattern="/echo/files/{*rest}", responses=body("rest")
    )
    await person.rule(
        name="prefix", matchType="Prefix", pattern="/echo/reports/", responses=body("prefix")
    )
    await person.rule(
        name="regex",
        matchType="Regex",
        pattern=r"^/echo/(goods|stuff)/\d+$",
        responses=body("regex"),
    )

    async def all_loaded() -> bool:  # rules load one NOTIFY at a time; wait for the last one
        return await served("/echo/stuff/7") == "regex" and await served("/echo/orders") == "exact"

    await eventually(all_loaded, what="the five rules")
    assert await served("/echo/orders/") == "exact"
    assert await served("/echo/ORDERS") == "exact"
    assert await served("/echo/items/42") == "template"
    assert await served("/echo/items/42/more") is None  # one segment only
    assert await served("/echo/files") == "rest"  # zero segments
    assert await served("/echo/files/a/b/c") == "rest"
    assert await served("/echo/reports/2026/q1") == "prefix"
    assert await served("/echo/stuff/7") == "regex"
    assert await served("/echo/stuff/x") is None
    assert await served("/echo/unmatched") is None  # no rule: proxied

    # Method filter and conditions.

    async def post_loaded() -> bool:
        return (await person.call("POST", "/echo/m")).headers["x-mockan-source"] == "mock"

    await person.rule(name="post", method="POST", pattern="/echo/m", responses=body("post"))
    await person.rule(
        name="conditions",
        pattern="/echo/c",
        queryConditions=[
            {"key": "page", "operator": "equals", "value": "2"},
            {"key": "debug", "operator": "exists"},
        ],
        headerConditions=[{"key": "X-Tenant", "operator": "equals", "value": "a"}],
        responses=body("conditions"),
    )

    async def conditions_loaded() -> bool:
        return await served("/echo/c?page=2&debug", headers={"x-tenant": "a"}) == "conditions"

    await eventually(conditions_loaded, what="the condition rule")
    await eventually(post_loaded, what="the POST rule")
    assert await served("/echo/m") is None  # GET, the rule wants POST
    assert (await person.call("POST", "/echo/m")).json() == {"rule": "post"}
    full = {"headers": {"x-tenant": "a"}}  # header names are case-insensitive, values are not
    assert await served("/echo/c?page=2&debug", **full) == "conditions"
    assert await served("/echo/c?page=3&debug", **full) is None
    assert await served("/echo/c?page=2", **full) is None
    assert await served("/echo/c?page=2&debug", headers={"x-tenant": "A"}) is None

    # Precedence on one path, peeled off one rule at a time: Exact > Template > Prefix > Regex.
    path = "/echo/p/1"
    rules = {
        "regex": await person.rule(
            name="p-regex", matchType="Regex", pattern=r"^/echo/p/\d+$", responses=body("regex")
        ),
        "prefix": await person.rule(
            name="p-prefix", matchType="Prefix", pattern="/echo/p/", responses=body("prefix")
        ),
        "template": await person.rule(
            name="p-template",
            matchType="Template",
            pattern="/echo/p/{id}",
            responses=body("template"),
        ),
        "exact": await person.rule(name="p-exact", pattern=path, responses=body("exact")),
    }
    order = []
    for name in ("exact", "template", "prefix", "regex"):

        async def winner_is_now(expected: str = name) -> bool:
            return await served(path) == expected

        await eventually(winner_is_now, what=f"{name} to win")
        order.append(await served(path))
        await person.toggle(rules[name], False)
    assert order == ["exact", "template", "prefix", "regex"]
    # Priority beats the type, a longer pattern beats a shorter one, older beats newer.
    for rule in rules.values():
        await person.toggle(rule, True)
    low = await person.rule(
        name="p-low", matchType="Prefix", pattern="/echo/", priority=1, responses=body("priority")
    )

    async def priority_wins() -> bool:
        return await served(path) == "priority"

    await eventually(priority_wins, what="the priority rule to win")
    await person.toggle(low, False)
    await person.rule(
        name="p-longer", matchType="Prefix", pattern="/echo/p/1", responses=body("longer")
    )
    await person.toggle(rules["exact"], False)
    await person.toggle(rules["template"], False)

    async def longer_wins() -> bool:  # longer than `/echo/p/`, though both are Prefix
        return await served(path) == "longer"

    await eventually(longer_wins, what="the longer pattern to win")

    # Patterns that RE2 or the rules can't take are rejected when saved.
    bad = {
        "regex_too_long": ("Regex", "^/" + "a" * 600),
        "backreference": ("Regex", r"^/(a)\1"),
        "lookahead": ("Regex", "^/a(?=b)"),
        "no_slash": ("Exact", "echo"),
        "template_rest": ("Template", "/a/{*r}/b"),
    }
    for label, (match_type, pattern) in bad.items():
        refused = await person.api.post(
            "/api/v1/me/rules",
            json={
                "name": label,
                "matchType": match_type,
                "pattern": pattern,
                "responses": [response_body()],
            },
        )
        assert refused.status_code == 422, label
        assert "pattern" in refused.json()["errors"], label


# ---- PR-06 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-06")
async def test_pr_06_a_rule_answers_with_its_status_headers_content_type_body_and_delay(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    await person.rule(
        pattern="/echo/teapot",
        responses=[
            response_body(
                statusCode=418,
                headers={"X-Flavour": "earl-grey", "Cache-Control": "no-store"},
                contentType="text/plain; charset=utf-8",
                body="short and stout ☕",
                delayMs=400,
            )
        ],
    )
    await person.becomes("/echo/teapot", source="mock")

    started = time.perf_counter()
    response = await person.get("/echo/teapot")
    elapsed = time.perf_counter() - started

    assert response.status_code == 418
    assert response.headers["x-flavour"] == "earl-grey"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.text == "short and stout ☕"
    assert elapsed >= 0.4

    # Defaults: `application/json`, no delay; the limits are enforced when saving.
    await person.rule(
        pattern="/echo/defaults", responses=[{"name": "bare", "statusCode": 200, "body": "{}"}]
    )
    await person.becomes("/echo/defaults", source="mock")
    defaults = await person.get("/echo/defaults")
    assert defaults.headers["content-type"] == "application/json"
    for bad in (
        response_body(statusCode=99),
        response_body(statusCode=600),
        response_body(delayMs=30_001),
        response_body(body="x" * (1_048_576 + 1)),
    ):
        refused = await person.api.post(
            "/api/v1/me/rules",
            json={"name": "n", "matchType": "Exact", "pattern": "/echo/x", "responses": [bad]},
        )
        assert refused.status_code == 422
    maximum = response_body(statusCode=599, delayMs=30_000, body="x" * 1_048_576)
    accepted = await person.api.post(
        "/api/v1/me/rules",
        json={"name": "max", "matchType": "Exact", "pattern": "/echo/max", "responses": [maximum]},
    )
    assert accepted.status_code == 201


# ---- PR-07 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-07")
async def test_pr_07_saving_enabling_and_disabling_apply_within_two_seconds(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    path = "/echo/hot"
    assert (await person.get(path)).headers["x-mockan-source"] == "proxy"

    # Each step is measured from the moment the Admin answers to the first request that shows it.
    rule = await person.rule(pattern=path)
    assert await person.becomes(path, source="mock") < TWO_SECONDS  # saved
    await person.toggle(rule, False)
    assert await person.becomes(path, source="proxy") < TWO_SECONDS  # disabled
    await person.toggle(rule, True)
    assert await person.becomes(path, source="mock") < TWO_SECONDS  # enabled
    await person.api.put(
        f"/api/v1/me/rules/{rule['id']}/responses/{rule['activeResponseId']}",
        json=response_body(body='{"edited":true}'),
    )

    async def edited() -> bool:
        return (await person.get(path)).json() == {"edited": True}

    assert await eventually(edited, what="the edited response") < TWO_SECONDS
    await person.api.delete(f"/api/v1/me/rules/{rule['id']}")
    assert await person.becomes(path, source="proxy") < TWO_SECONDS  # deleted
    # The Gateway keeps serving from memory: "no DB access while handling a request" is
    # tests/gateway/test_pipeline.py; "degraded when the DB is down" is test_snapshot_service.py.


# ---- PR-08 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-08")
async def test_pr_08_one_rule_or_all_rules_can_be_switched_off_and_on_again(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    first = await person.rule(name="first", pattern="/echo/one")
    await person.rule(name="second", pattern="/echo/two")
    await person.becomes("/echo/one", source="mock")
    await person.becomes("/echo/two", source="mock")

    await person.toggle(first, False)  # a single switch
    await person.becomes("/echo/one", source="proxy")
    assert (await person.get("/echo/two")).headers["x-mockan-source"] == "mock"

    off = await person.post("/me/rules/toggle-all", {"isEnabled": False})
    assert off.json() == {"updated": 1}  # only the rule that was still on
    await person.becomes("/echo/two", source="proxy")

    # Disabled rules stay saved, unchanged, and come back without editing.
    saved = (await person.api.get("/api/v1/me/rules")).json()
    assert [r["isEnabled"] for r in saved] == [False, False]
    assert [r["pattern"] for r in saved] == ["/echo/one", "/echo/two"]
    on = await person.post("/me/rules/toggle-all", {"isEnabled": True})
    assert on.json() == {"updated": 2}
    await person.becomes("/echo/one", source="mock")
    await person.becomes("/echo/two", source="mock")


# ---- PR-09 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-09")
async def test_pr_09_every_response_says_where_it_came_from(stack: Stack, root: Person) -> None:
    person = await dev(stack)
    origin = {"origin": LOCALHOST}
    rule = await person.rule()
    await person.becomes("/echo/mocked", source="mock")

    mocked = await person.get("/echo/mocked", headers=origin)
    proxied = await person.get("/echo", headers=origin)
    error = await stack.gateway_client.get("/nobody/echo", headers=origin)
    preflight = await person.call(
        "OPTIONS", "/echo", headers={**origin, "access-control-request-method": "GET"}
    )

    assert mocked.headers["x-mockan-source"] == "mock"
    assert mocked.headers["x-mockan-rule-id"] == rule["id"]
    assert proxied.headers["x-mockan-source"] == "proxy"
    assert "x-mockan-rule-id" not in proxied.headers
    assert error.headers["x-mockan-source"] == "error"
    assert preflight.headers["x-mockan-source"] == "mock"  # TODO(OQ-B2)
    for response in (mocked, proxied, error):
        exposed = response.headers["access-control-expose-headers"].lower()
        assert "x-mockan-source" in exposed and "x-mockan-rule-id" in exposed


# ---- PR-10 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-10")
async def test_pr_10_admins_manage_the_catalog_and_developers_only_read_it(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    service = await stack.add_service(
        root, "limsa", stage=stack.upstream.url, dev=stack.upstream.url
    )

    # Create / edit / delete, as an admin.
    listed = {s["name"]: s for s in (await root.api.get("/api/v1/services")).json()}
    assert [e["environment"] for e in listed["limsa"]["environments"]] == ["dev", "stage"]
    edited = await root.put(
        f"/services/{service['id']}",
        {
            "name": "limsa",
            "pathPrefix": "/limsa",
            "stripPrefix": True,
            "rewriteOrigin": True,
            "defaultEnvironment": "dev",
        },
    )
    assert (edited.json()["stripPrefix"], edited.json()["rewriteOrigin"]) == (True, True)
    environment = listed["limsa"]["environments"][0]
    await root.put(
        f"/services/{service['id']}/environments/{environment['id']}",
        {
            "environment": "dev",
            "baseUrl": stack.upstream.url,
            "timeoutSeconds": 5,
            "extraHeaders": {"X-Env": "dev"},
        },
    )
    unique_name = await root.api.post(
        "/api/v1/services", json={"name": "limsa", "pathPrefix": "/other"}
    )
    unique_prefix = await root.api.post(
        "/api/v1/services", json={"name": "other", "pathPrefix": "/LIMSA"}
    )
    assert (unique_name.status_code, unique_name.json()["code"]) == (409, "name_taken")
    assert (unique_prefix.status_code, unique_prefix.json()["code"]) == (409, "path_prefix_taken")

    # A developer reads but doesn't write.
    assert "limsa" in {s["name"] for s in (await person.api.get("/api/v1/services")).json()}
    for method, path, body in (
        ("POST", "/api/v1/services", {"name": "x", "pathPrefix": "/x"}),
        ("PUT", f"/api/v1/services/{service['id']}", {"name": "limsa", "pathPrefix": "/limsa"}),
        ("DELETE", f"/api/v1/services/{service['id']}", None),
    ):
        refused = await person.api.request(method, path, json=body)
        assert (refused.status_code, refused.json()["code"]) == (403, "forbidden"), method

    assert (await root.api.delete(f"/api/v1/services/{service['id']}")).status_code == 204
    assert "limsa" not in {s["name"] for s in (await root.api.get("/api/v1/services")).json()}


# ---- PR-15 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-15")
async def test_pr_15_upstreams_are_allowlisted_workspaces_are_private_and_changes_are_audited(
    stack: Stack, root: Person
) -> None:
    alice, bob = await dev(stack, "alice"), await dev(stack, "bob")

    # Only allowlisted hosts can be saved; production hosts never are.
    service = await stack.add_service(root, "guarded")
    for url in (
        "https://prod.novin-tools.com",
        "http://169.254.169.254",
        "https://evil.example.com",
    ):
        refused = await root.api.post(
            f"/api/v1/services/{service['id']}/environments",
            json={"environment": "dev", "baseUrl": url},
        )
        assert refused.status_code == 422, url
        assert refused.json()["code"] == "upstream_host_not_allowed"

    # Authentication is required, and a developer can't see or change another's workspace.
    assert (
        await httpx.AsyncClient(base_url=stack.admin.url).get("/api/v1/me/rules")
    ).status_code == 401
    rule = await alice.rule(
        responses=[response_body(headers={"Authorization": "Bearer hunter2", "X-Api-Key": "k"})]
    )
    assert (await bob.api.get("/api/v1/me/rules")).json() == []
    for method, path in (("GET", f"/me/rules/{rule['id']}"), ("DELETE", f"/me/rules/{rule['id']}")):
        assert (await bob.api.request(method, f"/api/v1{path}")).status_code == 404

    # Rule changes are audited (who, when, what), with secrets masked.
    await alice.toggle(rule, False)
    async with stack.session_factory() as session:
        rows = list(await session.scalars(select(AuditLog).order_by(AuditLog.id)))
    mine = [r for r in rows if r.entity_id == rule["id"]]
    assert [r.action.value for r in mine] == ["create", "toggle"]
    assert all(r.developer_id is not None and r.timestamp is not None for r in mine)
    assert mine[0].changes["responses"][0]["headers"] == {
        "Authorization": "***",
        "X-Api-Key": "***",
    }
    assert "hunter2" not in str([r.changes for r in rows])


# ---- PR-16 ---------------------------------------------------------------------------------


@pytest.mark.req("PR-16")
async def test_pr_16_mockan_errors_are_problem_json_with_the_slug_and_the_path(
    stack: Stack, root: Person
) -> None:
    person = await dev(stack)
    await stack.add_service(root, "closed", stage="http://127.0.0.1:1")  # nothing listens there
    # Prefix `/t` is stripped, so `/t/slow` lands on the upstream's `/slow`; a 1 s timeout is hit.
    await stack.add_service(
        root, "impatient", prefix="/t", strip_prefix=True, timeout_seconds=1,
        stage=stack.upstream.url,
    )  # fmt: skip

    async def registered() -> bool:
        probes = [await person.get("/closed/x"), await person.get("/t/slow?seconds=0")]
        return all("service_not_resolved" not in r.text for r in probes)

    await eventually(registered, what="the new Services")

    cases = {
        "developer_not_found": (
            await stack.gateway_client.get("/mistyped/echo/x?y=1"),
            404,
            "mistyped",
            "/mistyped/echo/x",
        ),
        "service_not_resolved": (
            await person.get("/nothing-registered/x"),
            502,
            "ehtesham",
            "/ehtesham/nothing-registered/x",
        ),
        "upstream_unreachable": (
            await person.get("/closed/x"),
            502,
            "ehtesham",
            "/ehtesham/closed/x",
        ),
        "upstream_timeout": (
            await person.get("/t/slow?seconds=3"),
            504,
            "ehtesham",
            "/ehtesham/t/slow",
        ),
    }
    for code, (response, status, slug, path) in cases.items():
        assert response.status_code == status, (code, response.text)
        assert response.headers["content-type"] == "application/problem+json", code
        body = response.json()
        assert (body["code"], body["status"]) == (code, status)
        assert body["title"] and body["detail"]
        assert body["type"].endswith(f"/problems/{code}")
        assert body["developer"] == slug, code
        assert body["path"] == path, code
        assert response.headers["x-mockan-source"] == "error"
