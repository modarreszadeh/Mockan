"""Gateway pipeline: Developer resolution, CORS, mocks and problems (arch §6.2, PR-01…PR-16)."""

import time

import pytest

from mockan.domain.enums import MatchType
from tests.gateway.conftest import ClientFactory
from tests.support.snapshot_builder import SnapshotBuilder, equals, exists

pytestmark = pytest.mark.asyncio


# ---- Developer resolution (PR-01, PR-16) ---------------------------------------------------------


@pytest.mark.req("PR-16")
async def test_unknown_slug_is_a_developer_not_found_problem_with_slug_and_path(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham")
    response = await gateway_client(snapshot_builder.build()).get("/nobody/limsa/api/v1/dashboard")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-mockan-source"] == "error"
    assert response.json() == {
        "type": "https://mock.test/problems/developer_not_found",
        "title": "Developer not found",
        "status": 404,
        "code": "developer_not_found",
        "detail": "No enabled Developer with slug 'nobody'.",
        "developer": "nobody",
        "path": "/nobody/limsa/api/v1/dashboard",
    }


@pytest.mark.req("PR-01")
async def test_disabled_developer_is_not_found(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("sleepy", is_enabled=False)
    snapshot_builder.rule(dev, MatchType.PREFIX, "/")
    response = await gateway_client(snapshot_builder.build()).get("/sleepy/x")
    assert response.status_code == 404
    assert response.json()["code"] == "developer_not_found"


@pytest.mark.req("PR-01")
@pytest.mark.parametrize(
    "path", ["/", "", "/_mockan", "/_mockan/other", "/api/v1/me", "/hubs/x", "/health"]
)
async def test_missing_and_reserved_slugs_are_not_found_even_with_a_matching_developer(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder, path: str
) -> None:
    for slug in ("api", "hubs", "health", "_mockan"):
        dev = snapshot_builder.developer(slug)  # can't exist in practice; the Gateway still refuses
        snapshot_builder.rule(dev, MatchType.PREFIX, "/")
    response = await gateway_client(snapshot_builder.build()).get(path or "/")
    assert response.status_code == 404
    assert response.json()["code"] == "developer_not_found"
    assert response.headers["x-mockan-source"] == "error"


@pytest.mark.req("PR-01")
async def test_slug_lookup_ignores_case(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/x", body='{"ok":1}')
    response = await gateway_client(snapshot_builder.build()).get("/EHTESHAM/x")
    assert response.status_code == 200


@pytest.mark.req("PR-01")
async def test_developers_are_isolated_end_to_end(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    alice, bob = snapshot_builder.developer("alice"), snapshot_builder.developer("bob")
    snapshot_builder.rule(alice, MatchType.EXACT, "/limsa/x", body='"alice"', status=201)
    snapshot_builder.rule(bob, MatchType.EXACT, "/limsa/x", body='"bob"', status=202)
    client = gateway_client(snapshot_builder.build())
    a, b = await client.get("/alice/limsa/x"), await client.get("/bob/limsa/x")
    assert (a.status_code, a.text) == (201, '"alice"')
    assert (b.status_code, b.text) == (202, '"bob"')


# ---- Mock responses (PR-06, PR-09, PR-05) --------------------------------------------------------


@pytest.mark.req("PR-06")
async def test_mock_serves_status_headers_content_type_and_body(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    rule = snapshot_builder.rule(
        dev, MatchType.EXACT, "/limsa/api/v1/dashboard", status=202, body='{"total":3}'
    )
    response = await gateway_client(snapshot_builder.build()).get(
        "/ehtesham/limsa/api/v1/dashboard"
    )
    assert response.status_code == 202
    assert response.text == '{"total":3}'
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-length"] == str(len(b'{"total":3}'))
    assert response.headers["x-mockan-source"] == "mock"
    assert response.headers["x-mockan-rule-id"] == str(rule.id)


@pytest.mark.req("PR-06")
async def test_mock_headers_are_applied_and_framing_headers_are_not(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev,
        MatchType.EXACT,
        "/h",
        body="héllo",
        response_headers={
            "X-Custom": "1",
            "Content-Length": "999",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Content-Type": "text/evil",
            "X-Mockan-Source": "proxy",
            "Bad\r\nName": "x",
            "X-Split": "a\r\nSet-Cookie: pwned=1",
        },
        content_type="text/plain; charset=utf-8",
    )
    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/h")
    assert response.headers["x-custom"] == "1"
    assert response.headers["content-length"] == str(len("héllo".encode()))
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["x-mockan-source"] == "mock"
    assert "transfer-encoding" not in response.headers
    assert "connection" not in response.headers
    assert "x-split" not in response.headers
    assert "set-cookie" not in response.headers
    assert response.text == "héllo"


@pytest.mark.req("PR-06")
@pytest.mark.parametrize("status", [204, 304])
async def test_bodyless_statuses_send_no_body(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder, status: int
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/n", status=status, body="ignored")
    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/n")
    assert response.status_code == status
    assert response.content == b""


@pytest.mark.req("PR-06")
async def test_mock_delay_is_applied_without_blocking_other_requests(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    import asyncio

    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/slow", delay_ms=300)
    snapshot_builder.rule(dev, MatchType.EXACT, "/fast")
    client = gateway_client(snapshot_builder.build())

    started = time.perf_counter()
    slow = asyncio.create_task(client.get("/ehtesham/slow"))
    await asyncio.sleep(0.02)
    fast_started = time.perf_counter()
    fast = await client.get("/ehtesham/fast")
    fast_elapsed = time.perf_counter() - fast_started
    await slow
    assert time.perf_counter() - started >= 0.3
    assert fast.status_code == 200
    assert fast_elapsed < 0.2  # the event loop was free while the slow mock slept


@pytest.mark.req("PR-05")
async def test_conditions_and_method_decide_whether_the_mock_answers(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev,
        MatchType.EXACT,
        "/search",
        method="POST",
        query=[equals("page", "2")],
        headers=[exists("x-debug")],
        body='"matched"',
    )
    client = gateway_client(snapshot_builder.build())
    hit = await client.post("/ehtesham/search?page=2", headers={"X-Debug": "1"})
    assert hit.text == '"matched"'
    assert hit.headers["x-mockan-source"] == "mock"
    for miss in (
        await client.get("/ehtesham/search?page=2", headers={"X-Debug": "1"}),
        await client.post("/ehtesham/search?page=3", headers={"X-Debug": "1"}),
        await client.post("/ehtesham/search?page=2"),
    ):
        assert miss.headers["x-mockan-source"] == "error"  # no rule, no Service: not resolved


@pytest.mark.req("PR-05")
async def test_precedence_and_template_params_through_the_gateway(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/limsa/", body='"prefix"')
    snapshot_builder.rule(dev, MatchType.TEMPLATE, "/limsa/orders/{id}", body='"template"')
    client = gateway_client(snapshot_builder.build())
    assert (await client.get("/ehtesham/limsa/orders/7")).text == '"template"'
    assert (await client.get("/ehtesham/limsa/other")).text == '"prefix"'


# ---- Problems for everything that is not a rule (PR-16, PR-09) -----------------------------------


@pytest.mark.req("PR-16")
async def test_no_matching_service_is_a_service_not_resolved_problem(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("limsa", "/limsa")
    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/nothing-registered/x")
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "service_not_resolved"
    assert body["developer"] == "ehtesham"
    assert body["path"] == "/ehtesham/nothing-registered/x"
    assert "'/nothing-registered/x'" in body["detail"]
    assert response.headers["x-mockan-source"] == "error"
    assert dev.slug == "ehtesham"


@pytest.mark.req("PR-16")
async def test_an_unexpected_exception_is_an_internal_error_problem_with_cors(
    gateway_client: ClientFactory,
    snapshot_builder: SnapshotBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("kaboom with secret-token-123")

    monkeypatch.setattr("mockan.gateway.middleware.mock_matching.match_request", boom)
    response = await gateway_client(snapshot_builder.build()).get(
        "/ehtesham/x", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["developer"] == "ehtesham"
    assert "kaboom" not in response.text  # never leak internals
    assert response.headers["x-mockan-source"] == "error"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---- CORS (PR-03, PR-09, D-13) -------------------------------------------------------------------

ORIGIN = "http://localhost:5173"


@pytest.mark.req("PR-03")
async def test_preflight_is_answered_with_204_and_never_reaches_a_rule(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/", body='"should not be served"')
    response = await gateway_client(snapshot_builder.build()).options(
        "/ehtesham/limsa/api/v1/dashboard",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert response.status_code == 204
    assert response.content == b""
    assert "x-mockan-rule-id" not in response.headers
    assert response.headers["x-mockan-source"] == "mock"  # OQ-B2
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-methods"] == "PUT"
    assert response.headers["access-control-allow-headers"] == "authorization, content-type"
    assert response.headers["access-control-max-age"] == "600"
    assert "Origin" in response.headers["vary"]


@pytest.mark.req("PR-03")
async def test_preflight_from_a_disallowed_origin_gets_204_without_allow_headers(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham")
    response = await gateway_client(snapshot_builder.build()).options(
        "/ehtesham/x",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 204
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.req("PR-03")
async def test_unknown_slug_preflight_and_errors_use_the_default_origins(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    client = gateway_client(snapshot_builder.build())
    preflight = await client.options(
        "/nobody/x", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    error = await client.get("/nobody/x", headers={"Origin": ORIGIN})
    assert error.status_code == 404
    assert error.headers["access-control-allow-origin"] == ORIGIN  # the browser can read the error
    blocked = await client.get("/nobody/x", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


@pytest.mark.req("PR-03")
async def test_origin_is_echoed_only_when_the_developer_allows_it(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer(
        "ehtesham", origins=["http://localhost:*", "https://app.example.com"]
    )
    snapshot_builder.rule(dev, MatchType.EXACT, "/x")
    client = gateway_client(snapshot_builder.build())

    for allowed in (ORIGIN, "https://app.example.com"):
        response = await client.get("/ehtesham/x", headers={"Origin": allowed})
        assert response.headers["access-control-allow-origin"] == allowed
        assert response.headers["access-control-allow-credentials"] == "true"
        assert response.headers["access-control-expose-headers"] == (
            "X-Mockan-Source, X-Mockan-Rule-Id"
        )
        assert "Origin" in response.headers["vary"]
    for denied in ("https://evil.example", "http://localhost:1.evil.com", "null"):
        response = await client.get("/ehtesham/x", headers={"Origin": denied})
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers
        assert "access-control-expose-headers" not in response.headers
        assert "Origin" in response.headers["vary"]  # still varies, so caches stay correct
    no_origin = await client.get("/ehtesham/x")
    assert "access-control-allow-origin" not in no_origin.headers


@pytest.mark.req("PR-03")
async def test_cors_headers_set_by_a_mock_are_replaced_by_mockans(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev,
        MatchType.EXACT,
        "/x",
        response_headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "false",
            "Vary": "Accept-Encoding",
        },
    )
    response = await gateway_client(snapshot_builder.build()).get(
        "/ehtesham/x", headers={"Origin": ORIGIN}
    )
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Accept-Encoding, Origin"
    without_origin = await gateway_client(snapshot_builder.build()).get("/ehtesham/x")
    assert "access-control-allow-origin" not in without_origin.headers  # the mock's `*` is gone


@pytest.mark.req("PR-09")
async def test_every_response_kind_carries_x_mockan_source(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/mocked")
    client = gateway_client(snapshot_builder.build())
    cases = {
        "mock": await client.get("/ehtesham/mocked"),
        "error": await client.get("/ehtesham/unmatched"),
    }
    cases["preflight"] = await client.options(
        "/ehtesham/mocked", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}
    )
    assert cases["mock"].headers["x-mockan-source"] == "mock"
    assert cases["error"].headers["x-mockan-source"] == "error"
    assert cases["preflight"].headers["x-mockan-source"] == "mock"
    assert (await client.get("/unknown/x")).headers["x-mockan-source"] == "error"
    assert (await client.get("/_mockan/health/live")).headers["x-mockan-source"] == "mock"


@pytest.mark.req("PR-09")
async def test_non_preflight_options_requests_are_not_treated_as_preflights(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/x", method="OPTIONS", body='"real options"')
    response = await gateway_client(snapshot_builder.build()).options(
        "/ehtesham/x",
        headers={"Origin": ORIGIN},  # no Access-Control-Request-Method
    )
    assert response.text == '"real options"'
