"""Templated mock bodies are rendered per request; failures: `mock_render_failed` (PR-19)."""

import json
import time
from typing import Any

import pytest

from mockan.domain.enums import BodyMode, MatchType
from tests.gateway.conftest import ClientFactory
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = [pytest.mark.asyncio, pytest.mark.req("PR-19")]


def template(
    builder: SnapshotBuilder,
    pattern: str,
    body: str,
    *,
    match_type: MatchType = MatchType.TEMPLATE,
    **kwargs: Any,
) -> None:
    dev = builder.developer("ehtesham")
    builder.rule(dev, match_type, pattern, body=body, body_mode=BodyMode.TEMPLATE, **kwargs)


async def test_route_params_query_headers_and_fake_data_are_rendered_per_request(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(
        snapshot_builder,
        "/limsa/orders/{id}",
        '{"id":{{ route.id }},"page":"{{ request.query.page }}",'
        '"tenant":"{{ request.headers["x-tenant"] }}",'
        '"who":"{{ fake.name() }}","path":"{{ request.path }}"}',
    )
    client = gateway_client(snapshot_builder.build())

    first = await client.get("/ehtesham/limsa/orders/42?page=2", headers={"x-tenant": "acme"})
    second = await client.get("/ehtesham/limsa/orders/43?page=3", headers={"x-tenant": "zeta"})

    assert first.status_code == 200
    assert first.headers["x-mockan-source"] == "mock"
    assert first.headers["content-type"] == "application/json"
    a, b = first.json(), second.json()
    assert (a["id"], a["page"], a["tenant"], a["path"]) == (42, "2", "acme", "/limsa/orders/42")
    assert (b["id"], b["page"], b["tenant"]) == (43, "3", "zeta")
    assert a["who"] and b["who"]


async def test_regex_groups_are_route_params_too(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(
        snapshot_builder,
        r"^/limsa/(?P<kind>goods|items)/(?P<n>\d+)$",
        "{{ route.kind }}-{{ route.n }}",
        match_type=MatchType.REGEX,
    )

    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/limsa/goods/7")

    assert response.text == "goods-7"


async def test_a_static_body_is_never_interpreted(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/x", body="{{ route.id }} {% broken")

    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/x")

    assert response.text == "{{ route.id }} {% broken"


async def test_a_render_error_is_a_mock_render_failed_problem_with_the_reason(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(snapshot_builder, "/limsa/orders/{id}", "{{ route.missing }}", name="Orders")
    client = gateway_client(snapshot_builder.build())

    response = await client.get("/ehtesham/limsa/orders/1")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-mockan-source"] == "error"
    body = response.json()
    assert body["code"] == "mock_render_failed"
    assert body["developer"] == "ehtesham"
    assert body["path"] == "/ehtesham/limsa/orders/1"
    assert "Orders" in body["detail"] and "missing" in body["detail"]
    assert body["type"].endswith("/problems/mock_render_failed")


async def test_a_template_that_renders_too_much_fails_cleanly(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(
        snapshot_builder,
        "/big",
        "{% for i in range(1000) %}{% for j in range(2) %}"
        + "x" * 1000
        + "{% endfor %}{% endfor %}",
    )

    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/big")

    assert response.status_code == 500
    assert "larger than 1 MB" in response.json()["detail"]


async def test_a_bodyless_status_skips_rendering(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(snapshot_builder, "/gone", "{{ route.missing }}", status=204)

    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/gone")

    assert (response.status_code, response.content) == (204, b"")


async def test_the_delay_applies_before_rendering(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(snapshot_builder, "/slow", "ok", delay_ms=150)

    started = time.perf_counter()
    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/slow")

    assert response.text == "ok"
    assert time.perf_counter() - started >= 0.15


async def test_a_json_response_with_dynamic_values_stays_valid_json(
    gateway_client: ClientFactory, snapshot_builder: SnapshotBuilder
) -> None:
    template(
        snapshot_builder,
        "/list",
        "[{% for i in range(request.query.n | int) %}"
        '{"i":{{ i }},"id":"{{ fake.uuid4() }}"}'
        "{% if not loop.last %},{% endif %}{% endfor %}]",
    )

    response = await gateway_client(snapshot_builder.build()).get("/ehtesham/list?n=5")

    items = json.loads(response.text)
    assert [item["i"] for item in items] == [0, 1, 2, 3, 4]
    assert len({item["id"] for item in items}) == 5
