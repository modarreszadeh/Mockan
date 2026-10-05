"""WebSocket bridge: echo, close codes, subprotocols, handshake headers and refusals (D-15, PR-02).

Real sockets all the way: browser-side client -> Gateway (Uvicorn) -> fake upstream (Uvicorn).
"""

import asyncio
import json
from typing import Any

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from mockan.domain.enums import EnvironmentName
from mockan.matching.snapshot import RuleSnapshot
from tests.gateway.conftest import FakeUpstream, LiveGateway, LiveGatewayFactory
from tests.gateway.test_proxy import SLUG, dead_port, strip_snapshot
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = pytest.mark.asyncio


def open_socket(gateway: LiveGateway, path: str, **kwargs: Any) -> connect:
    """A client connection through the Gateway (never via an environment proxy)."""
    kwargs.setdefault("max_size", None)
    return connect(f"{gateway.ws_url}/{SLUG}/svc{path}", proxy=None, **kwargs)


async def refused_handshake(gateway: LiveGateway, path: str) -> InvalidStatus:
    with pytest.raises(InvalidStatus) as refused:
        async with open_socket(gateway, path):
            pass
    return refused.value


def snapshot(builder: SnapshotBuilder, upstream: FakeUpstream, **service: Any) -> RuleSnapshot:
    return strip_snapshot(builder, upstream, **service)


@pytest.mark.req("PR-02")
async def test_text_and_binary_frames_are_echoed_through_the_bridge(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws") as socket:
        await socket.send("héllo")
        assert await socket.recv() == "héllo"  # a text frame stays text
        await socket.send(b"\x00\x01\xff")
        assert await socket.recv() == b"\x00\x01\xff"  # a binary frame stays binary
        big = b"x" * (3 * 1024 * 1024)  # beyond the 1 MiB default of the websockets library
        await socket.send(big)
        assert await socket.recv() == big


@pytest.mark.req("PR-02")
async def test_an_upstream_close_code_and_reason_reach_the_browser(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws") as socket:
        await socket.send("close:4001:bye")
        with pytest.raises(ConnectionClosed) as closed:
            await socket.recv()
    assert closed.value.rcvd is not None
    assert (closed.value.rcvd.code, closed.value.rcvd.reason) == (4001, "bye")


@pytest.mark.req("PR-02")
async def test_a_browser_close_code_reaches_the_upstream(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws") as socket:
        await socket.send("ping")
        assert await socket.recv() == "ping"
        await socket.close(code=4002, reason="done")
    assert await asyncio.to_thread(fake_upstream.state.ws_closed.wait, 5)
    assert fake_upstream.state.ws_close_codes == [4002]


@pytest.mark.req("PR-02")
async def test_a_normal_close_is_normal_on_both_sides(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws") as socket:
        await socket.close()  # 1000
    assert await asyncio.to_thread(fake_upstream.state.ws_closed.wait, 5)
    assert fake_upstream.state.ws_close_codes == [1000]


@pytest.mark.req("PR-02")
async def test_the_upstreams_subprotocol_choice_is_offered_to_the_browser(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws/proto", subprotocols=["other", "chat"]) as socket:  # type: ignore[list-item]
        assert socket.subprotocol == "chat"
    async with open_socket(gateway, "/ws/proto", subprotocols=["other"]) as socket:  # type: ignore[list-item]
        assert socket.subprotocol is None


async def handshake_seen_by_upstream(socket: ClientConnection) -> dict[str, Any]:
    return dict(json.loads(await socket.recv()))


@pytest.mark.req("PR-02")
async def test_handshake_headers_are_transformed_like_http_ones(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(
        snapshot(snapshot_builder, fake_upstream, extra_headers={"x-api-key": "configured"})
    )
    async with open_socket(
        gateway,
        "/ws/headers?token=abc&x=%20y",
        origin="http://localhost:5173",  # type: ignore[arg-type]
        additional_headers={"Cookie": "a=1", "X-Api-Key": "from-browser"},
    ) as socket:
        seen = await handshake_seen_by_upstream(socket)
    headers: dict[str, list[str]] = {}
    for name, value in seen["headers"]:
        headers.setdefault(name, []).append(value)
    assert seen["path"] == "/ws/headers"
    assert seen["query"] == "token=abc&x=%20y"
    assert headers["host"] == [f"{fake_upstream.host}:{fake_upstream.server.port}"]
    assert headers["origin"] == ["http://localhost:5173"]  # once, unchanged
    assert headers["cookie"] == ["a=1"]
    assert headers["x-api-key"] == ["configured"]
    assert headers["x-forwarded-prefix"] == [f"/{SLUG}"]
    assert headers["x-mockan-developer"] == [SLUG]
    assert headers["x-forwarded-for"] == ["127.0.0.1"]
    # The upstream hop negotiated its own handshake: one key, one version, none of the browser's.
    assert len(headers["sec-websocket-key"]) == 1
    assert headers["sec-websocket-version"] == ["13"]
    assert headers["upgrade"] == ["websocket"]


@pytest.mark.req("PR-02")
async def test_the_browsers_user_agent_is_forwarded_not_the_libraries(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    async with open_socket(gateway, "/ws/headers", user_agent_header="Mozilla/5.0 Test") as socket:
        seen = await handshake_seen_by_upstream(socket)
    agents = [value for name, value in seen["headers"] if name == "user-agent"]
    assert agents == ["Mozilla/5.0 Test"]


@pytest.mark.req("PR-02")
async def test_an_upstream_that_refuses_the_upgrade_has_its_answer_passed_on(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    refused = await refused_handshake(gateway, "/ws/deny")
    assert refused.response.status_code == 401
    assert json.loads(refused.response.body or b"") == {"error": "unauthorized"}
    assert refused.response.headers["x-mockan-source"] == "proxy"


@pytest.mark.req("PR-16")
async def test_an_unknown_developer_is_a_404_problem_before_the_upgrade(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    with pytest.raises(InvalidStatus) as refused:
        async with connect(f"{gateway.ws_url}/nobody/svc/ws", proxy=None):
            pass
    response = refused.value.response
    body = json.loads(response.body or b"")
    assert response.status_code == 404
    assert response.headers["x-mockan-source"] == "error"
    assert response.headers["content-type"] == "application/problem+json"
    assert (body["code"], body["developer"], body["path"]) == (
        "developer_not_found",
        "nobody",
        "/nobody/svc/ws",
    )


@pytest.mark.req("PR-16")
async def test_a_path_no_service_owns_is_a_502_service_not_resolved_problem(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(snapshot(snapshot_builder, fake_upstream))
    with pytest.raises(InvalidStatus) as refused:
        async with connect(f"{gateway.ws_url}/{SLUG}/nothing/ws", proxy=None):
            pass
    assert refused.value.response.status_code == 502
    assert json.loads(refused.value.response.body or b"")["code"] == "service_not_resolved"


@pytest.mark.req("PR-16")
async def test_an_unreachable_upstream_is_a_502_problem(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        environments={EnvironmentName.STAGE: f"http://127.0.0.1:{dead_port()}"},
    )
    refused = await refused_handshake(live_gateway(snapshot_builder.build()), "/ws")
    assert refused.response.status_code == 502
    assert json.loads(refused.response.body or b"")["code"] == "upstream_unreachable"


@pytest.mark.req("PR-15")
async def test_the_allowlist_applies_to_websockets_too(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(
        snapshot(snapshot_builder, fake_upstream), allowed_upstream_hosts=["only.stage.internal"]
    )
    refused = await refused_handshake(gateway, "/ws")
    assert refused.response.status_code == 502
    assert json.loads(refused.response.body or b"")["code"] == "upstream_unreachable"
