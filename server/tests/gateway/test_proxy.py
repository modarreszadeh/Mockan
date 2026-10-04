"""Proxy fidelity, streaming, redirects, cookies, CORS and errors against a real upstream.

The Gateway and the fake upstream run on real Uvicorn sockets (never mocked), so streaming and
header handling are real (testing.md §3). Covers PR-02, PR-03, PR-04, PR-09, PR-15, NFR-01, NFR-04.
"""

import asyncio
import base64
import dataclasses
import gzip
import hashlib
import socket
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from mockan.domain.enums import EnvironmentName, MatchType
from mockan.matching.snapshot import RuleSnapshot
from tests.gateway.conftest import FakeUpstream, LiveGatewayFactory
from tests.support.fake_upstream import CHUNK, download_sha256
from tests.support.rss import RssSampler, rss_supported
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = pytest.mark.asyncio

SLUG = "ehtesham"
MEGABYTE = 1024 * 1024


def strip_snapshot(
    builder: SnapshotBuilder, upstream: FakeUpstream, **service: Any
) -> RuleSnapshot:
    """Developer `ehtesham` + Service `/svc` (StripPrefix): `/ehtesham/svc/x` -> upstream `/x`."""
    builder.developer(SLUG)
    builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        environments={EnvironmentName.STAGE: upstream.url},
        **service,
    )
    return builder.build()


async def echo(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = await client.request(method, f"/{SLUG}/svc{path}", **kwargs)
    assert response.status_code == 200, response.text
    return dict(response.json())


def echoed(body: dict[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, value in body["headers"]:
        grouped.setdefault(name, []).append(value)
    return grouped


# ---- fidelity (PR-02) ---------------------------------------------------------------------------


@pytest.mark.req("PR-02")
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def test_method_path_query_and_body_reach_the_upstream_unchanged(
    live_gateway: LiveGatewayFactory,
    fake_upstream: FakeUpstream,
    snapshot_builder: SnapshotBuilder,
    method: str,
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    payload = b'{"name":"\xc3\xbc","n":[1,2,3]}'
    body = await echo(
        gateway.client,
        method,
        "/echo/a%2Fb/c%20d/%E2%9C%93?a=1&b=%20x&flag&a=2&u=%C3%BC",
        content=payload if method not in {"GET", "OPTIONS"} else None,
        headers={"content-type": "application/json"},
    )
    assert body["method"] == method
    assert body["rawPath"] == "/echo/a%2Fb/c%20d/%E2%9C%93"  # `%2F` stays one segment
    assert body["query"] == "a=1&b=%20x&flag&a=2&u=%C3%BC"  # raw query, never re-encoded
    expected = payload if method not in {"GET", "OPTIONS"} else b""
    assert body["bodySha256"] == hashlib.sha256(expected).hexdigest()
    assert body["bodyLength"] == len(expected)


@pytest.mark.req("PR-02")
async def test_end_to_end_headers_are_forwarded_and_framing_headers_are_not_invented(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    sent = await echo(
        gateway.client,
        "GET",
        "/echo",
        headers={
            "authorization": "Bearer abc.def",
            "cookie": "a=1; b=2",
            "traceparent": traceparent,
            "x-custom": "yes",
            "accept-language": "fa,en;q=0.8",
        },
    )
    headers = echoed(sent)
    assert headers["authorization"] == ["Bearer abc.def"]
    assert headers["cookie"] == ["a=1; b=2"]
    assert headers["traceparent"] == [traceparent]
    assert headers["x-custom"] == ["yes"]
    assert headers["accept-language"] == ["fa,en;q=0.8"]
    assert "content-length" not in headers  # a GET stays body-less: no chunked framing invented
    assert "transfer-encoding" not in headers


@pytest.mark.req("PR-02")
async def test_host_is_the_upstreams_and_forwarding_headers_are_set(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    headers = echoed(
        await echo(
            gateway.client,
            "GET",
            "/echo",
            headers={"x-forwarded-prefix": "/spoofed", "x-mockan-developer": "someone-else"},
        )
    )
    assert headers["host"] == [f"{fake_upstream.host}:{fake_upstream.server.port}"]
    assert headers["x-forwarded-for"] == ["127.0.0.1"]
    assert headers["x-forwarded-proto"] == ["http"]
    assert headers["x-forwarded-host"] == [f"127.0.0.1:{gateway.server.port}"]
    assert headers["x-forwarded-prefix"] == [f"/{SLUG}"]
    assert headers["x-mockan-developer"] == [SLUG]


@pytest.mark.req("PR-02")
async def test_hop_by_hop_request_headers_are_dropped(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    headers = echoed(
        await echo(
            gateway.client,
            "GET",
            "/echo",
            headers={
                "connection": "keep-alive, x-secret-hop",
                "x-secret-hop": "1",
                "keep-alive": "timeout=5",
                "proxy-authorization": "Basic abc",
                "te": "trailers",
                "x-keep": "yes",
            },
        )
    )
    assert headers["x-keep"] == ["yes"]
    for name in ("x-secret-hop", "keep-alive", "proxy-authorization", "te"):
        assert name not in headers


@pytest.mark.req("PR-04")
async def test_extra_headers_of_the_environment_are_added_and_win(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot = strip_snapshot(
        snapshot_builder, fake_upstream, extra_headers={"x-api-key": "configured"}
    )
    headers = echoed(
        await echo(
            live_gateway(snapshot).client, "GET", "/echo", headers={"x-api-key": "from-browser"}
        )
    )
    assert headers["x-api-key"] == ["configured"]


@pytest.mark.req("PR-04")
async def test_rewrite_origin_replaces_the_browsers_origin(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot = strip_snapshot(snapshot_builder, fake_upstream, rewrite_origin=True)
    headers = echoed(
        await echo(
            live_gateway(snapshot).client,
            "GET",
            "/echo",
            headers={"origin": "http://localhost:5173", "referer": "http://localhost:5173/page"},
        )
    )
    assert headers["origin"] == [fake_upstream.url]
    assert headers["referer"] == [fake_upstream.url + "/"]


@pytest.mark.req("PR-02")
async def test_origin_is_forwarded_unchanged_by_default(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    headers = echoed(
        await echo(gateway.client, "GET", "/echo", headers={"origin": "http://localhost:5173"})
    )
    assert headers["origin"] == ["http://localhost:5173"]


@pytest.mark.req("PR-04")
async def test_without_strip_prefix_the_service_prefix_stays_in_the_upstream_path(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "echo", "/echo", strip_prefix=False, environments={EnvironmentName.STAGE: fake_upstream.url}
    )
    gateway = live_gateway(snapshot_builder.build())
    response = await gateway.client.get(f"/{SLUG}/echo/orders/42?x=1")
    assert response.json()["rawPath"] == "/echo/orders/42"
    assert response.json()["query"] == "x=1"


@pytest.mark.req("PR-04")
async def test_strip_prefix_removes_the_service_prefix(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    response = await gateway.client.get(f"/{SLUG}/svc/echo/orders/42")
    assert response.json()["rawPath"] == "/echo/orders/42"


@pytest.mark.req("PR-02")
@pytest.mark.parametrize("status", [200, 201, 204, 304, 404, 418, 500, 503])
async def test_status_codes_pass_through(
    live_gateway: LiveGatewayFactory,
    fake_upstream: FakeUpstream,
    snapshot_builder: SnapshotBuilder,
    status: int,
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    response = await gateway.client.get(f"/{SLUG}/svc/status/{status}")
    assert response.status_code == status
    assert response.headers["x-keep"] == "yes"
    assert response.headers["x-mockan-source"] == "proxy"


@pytest.mark.req("PR-02")
async def test_head_returns_the_upstreams_headers_and_no_body(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    direct = await gateway.client.head(f"{fake_upstream.url}/echo")
    via = await gateway.client.head(f"/{SLUG}/svc/echo")
    assert via.status_code == direct.status_code == 200
    assert via.content == b""
    assert via.headers["content-type"] == direct.headers["content-type"]
    assert int(via.headers["content-length"]) > 0  # the length GET would have had, no body sent
    assert via.headers["x-mockan-source"] == "proxy"


# ---- streaming (NFR-04) -------------------------------------------------------------------------


async def chunks(megabytes: int) -> AsyncIterator[bytes]:
    for _ in range(megabytes * 16):
        yield CHUNK


@pytest.mark.req("NFR-04")
async def test_a_chunked_upload_reaches_the_upstream_intact(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    body = await echo(gateway.client, "POST", "/echo", content=chunks(2))  # no Content-Length
    assert body["bodyLength"] == 2 * MEGABYTE
    assert body["bodySha256"] == download_sha256(2)
    assert echoed(body)["transfer-encoding"] == ["chunked"]


@pytest.mark.req("NFR-04")
async def test_an_empty_post_keeps_its_zero_content_length(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    body = await echo(gateway.client, "POST", "/echo")
    assert echoed(body)["content-length"] == ["0"]
    assert body["bodyLength"] == 0


@pytest.mark.req("NFR-04")
@pytest.mark.skipif(not rss_supported(), reason="needs /proc/self/statm")
async def test_a_10_mb_upload_and_download_stream_with_bounded_memory(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    await echo(gateway.client, "POST", "/echo", content=chunks(1))  # warm up pools and imports

    # Gateway, upstream and this client share one process: buffering anywhere would show up here.
    with RssSampler() as sampler:
        upload = await echo(gateway.client, "POST", "/echo", content=chunks(10))
        digest, size = hashlib.sha256(), 0
        async with gateway.client.stream("GET", f"/{SLUG}/svc/download?mb=10") as response:
            assert response.headers["content-length"] == str(10 * MEGABYTE)
            async for part in response.aiter_raw():
                digest.update(part)
                size += len(part)

    assert upload["bodyLength"] == 10 * MEGABYTE
    assert upload["bodySha256"] == download_sha256(10)
    assert (size, digest.hexdigest()) == (10 * MEGABYTE, download_sha256(10))
    assert sampler.growth_bytes < 20 * MEGABYTE, (
        f"RSS grew {sampler.growth_bytes / MEGABYTE:.1f} MB"
    )


@pytest.mark.req("NFR-04")
async def test_sse_events_arrive_while_the_stream_is_still_open(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    arrivals: list[float] = []
    received = ""
    async with gateway.client.stream("GET", f"/{SLUG}/svc/sse?count=4&interval=0.4") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        async for part in response.aiter_text():
            arrivals.append(time.monotonic())
            received += part
    assert received == "".join(f"data: {n}\n\n" for n in range(4))
    # A proxy that buffered would deliver everything at the end, at one instant.
    assert arrivals[-1] - arrivals[0] > 0.8


@pytest.mark.req("NFR-04")
async def test_the_upstream_stream_is_cancelled_when_the_client_disconnects(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    async with gateway.client.stream(
        "GET", f"/{SLUG}/svc/sse?count=1000&interval=0.05"
    ) as response:
        async for _ in response.aiter_raw():
            break  # one event is enough; leaving the block closes the connection
    assert await asyncio.to_thread(fake_upstream.state.sse_closed.wait, 5)


@pytest.mark.req("NFR-04")
async def test_an_upstream_that_dies_mid_body_makes_the_client_see_an_error_not_a_short_body(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    with pytest.raises(httpx.TransportError):
        async with gateway.client.stream("GET", f"/{SLUG}/svc/truncated") as response:
            assert response.status_code == 200  # headers were already sent
            await response.aread()
    # The Gateway is still healthy for the next request on a fresh connection.
    assert (await gateway.client.get(f"/{SLUG}/svc/status/204")).status_code == 204


@pytest.mark.req("PR-02")
async def test_the_body_is_passed_through_raw_so_content_encoding_survives(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    async with gateway.client.stream("GET", f"/{SLUG}/svc/gzip") as response:
        assert response.headers["content-encoding"] == "gzip"
        raw = b"".join([part async for part in response.aiter_raw()])
    assert int(response.headers["content-length"]) == len(raw)
    assert gzip.decompress(raw) == b"hello gateway " * 50


# ---- response rewriting (PR-03, PR-09) ----------------------------------------------------------


@pytest.mark.req("PR-03")
async def test_redirects_are_not_followed_and_location_points_back_at_mockan(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(
        strip_snapshot(snapshot_builder, fake_upstream), public_base_url="https://mock.test"
    )
    absolute = await gateway.client.get(f"/{SLUG}/svc/redirect")
    assert absolute.status_code == 302
    assert absolute.headers["location"] == f"https://mock.test/{SLUG}/svc/echo?via=redirect"

    relative = await gateway.client.get(f"/{SLUG}/svc/redirect-root")
    assert relative.status_code == 301
    assert relative.headers["location"] == f"/{SLUG}/svc/echo?via=root-relative"


@pytest.mark.req("PR-03")
async def test_location_of_a_created_resource_is_rewritten_too(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(
        strip_snapshot(snapshot_builder, fake_upstream), public_base_url="https://mock.test"
    )
    response = await gateway.client.post(f"/{SLUG}/svc/created")
    assert response.status_code == 201
    assert response.headers["location"] == f"https://mock.test/{SLUG}/svc/echo"


@pytest.mark.req("PR-03")
async def test_set_cookie_loses_its_domain_and_gets_a_slug_prefixed_path(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    response = await gateway.client.get(f"/{SLUG}/svc/set-cookie")
    assert response.headers.get_list("set-cookie") == [
        f"a=1; HttpOnly; Secure; Path=/{SLUG}/svc/x",
        f"b=2; Path=/{SLUG}/svc",
        f"c=3; SameSite=None; Secure; Path=/{SLUG}/svc",
    ]


@pytest.mark.req("PR-03")
async def test_upstream_cors_is_replaced_by_mockans(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    allowed = await gateway.client.get(
        f"/{SLUG}/svc/cors", headers={"origin": "http://localhost:5173"}
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    expose = allowed.headers["access-control-expose-headers"]
    assert expose == "X-Mockan-Source, X-Mockan-Rule-Id"
    assert allowed.headers["x-keep"] == "yes"

    refused = await gateway.client.get(f"/{SLUG}/svc/cors", headers={"origin": "https://evil.test"})
    assert "access-control-allow-origin" not in refused.headers  # the upstream's is gone too
    assert "access-control-expose-headers" not in refused.headers


@pytest.mark.req("PR-09")
async def test_proxied_responses_say_proxy_and_hide_the_upstreams_framing_and_identity(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    response = await gateway.client.get(f"/{SLUG}/svc/response-headers")
    assert response.headers["x-mockan-source"] == "proxy"
    assert "x-mockan-rule-id" not in response.headers
    assert response.headers["x-keep"] == "yes"
    for name in ("x-private", "keep-alive", "proxy-authenticate"):
        assert name not in response.headers
    assert response.headers["server"] != "fake-upstream"
    assert len(response.headers.get_list("date")) == 1  # Uvicorn's own, no duplicate


@pytest.mark.req("PR-04")
async def test_a_mock_rule_wins_and_unmatched_requests_are_proxied(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    developer = snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "svc", "/svc", strip_prefix=True, environments={EnvironmentName.STAGE: fake_upstream.url}
    )
    snapshot_builder.rule(developer, MatchType.EXACT, "/svc/echo", body='{"mocked":true}')
    gateway = live_gateway(snapshot_builder.build())
    mocked = await gateway.client.get(f"/{SLUG}/svc/echo")
    assert mocked.headers["x-mockan-source"] == "mock"
    assert mocked.json() == {"mocked": True}
    proxied = await gateway.client.get(f"/{SLUG}/svc/echo/other")
    assert proxied.headers["x-mockan-source"] == "proxy"
    assert proxied.json()["rawPath"] == "/echo/other"


# ---- environments (PR-04) -----------------------------------------------------------------------


@pytest.mark.req("PR-04")
async def test_switching_environment_takes_effect_after_a_snapshot_swap(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    # Two names for the same server, so the upstream can tell which environment was used.
    port = fake_upstream.server.port
    developer = snapshot_builder.developer(SLUG)
    service = snapshot_builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        default_environment=EnvironmentName.STAGE,
        environments={
            EnvironmentName.DEV: f"http://localhost:{port}",
            EnvironmentName.STAGE: f"http://127.0.0.1:{port}",
        },
    )
    before = snapshot_builder.build()
    gateway = live_gateway(before, allowed_upstream_hosts=["localhost", "127.0.0.1"])
    assert echoed(await echo(gateway.client, "GET", "/echo"))["host"] == [f"127.0.0.1:{port}"]

    dev_id = service.environments[EnvironmentName.DEV].id
    chose_dev = dataclasses.replace(developer, service_environment_ids={service.id: dev_id})
    gateway.provider.swap(RuleSnapshot.build(developers=[chose_dev], rules=[], services=[service]))
    assert echoed(await echo(gateway.client, "GET", "/echo"))["host"] == [f"localhost:{port}"]


# ---- errors (PR-15, PR-16) ----------------------------------------------------------------------


def dead_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.req("PR-16")
async def test_an_unreachable_upstream_is_a_502_upstream_unreachable_problem(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        environments={EnvironmentName.STAGE: f"http://127.0.0.1:{dead_port()}"},
    )
    gateway = live_gateway(snapshot_builder.build())
    response = await gateway.client.get(f"/{SLUG}/svc/echo?x=1")
    assert response.status_code == 502
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-mockan-source"] == "error"
    body = response.json()
    assert body["code"] == "upstream_unreachable"
    assert (body["developer"], body["path"]) == (SLUG, f"/{SLUG}/svc/echo")


@pytest.mark.req("PR-16")
async def test_a_slow_upstream_is_a_504_upstream_timeout_problem(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream, timeout_seconds=1))
    started = time.monotonic()
    response = await gateway.client.get(f"/{SLUG}/svc/slow?seconds=5")
    assert response.status_code == 504
    assert response.headers["x-mockan-source"] == "error"
    assert response.json()["code"] == "upstream_timeout"
    assert time.monotonic() - started < 4  # gave up at the Service's timeout, not at 5 s


@pytest.mark.req("PR-15")
async def test_a_destination_outside_the_allowlist_is_refused_without_connecting(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot = strip_snapshot(snapshot_builder, fake_upstream)
    gateway = live_gateway(snapshot, allowed_upstream_hosts=["only.stage.internal"])
    response = await gateway.client.get(f"/{SLUG}/svc/echo")
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_unreachable"
    assert "MOCKAN_ALLOWED_UPSTREAM_HOSTS" in response.json()["detail"]
    assert response.headers["x-mockan-source"] == "error"


@pytest.mark.req("PR-15")
@pytest.mark.parametrize(
    "base_url",
    [
        "http://allowed.test@evil.test/",  # userinfo trick: the host is evil.test
        "http://allowed.test.evil.test/",
        "http://evil.test/allowed.test",
        "http://evil.test:80#allowed.test",
        "ftp://allowed.test/",
    ],
)
async def test_allowlist_checks_the_host_the_client_would_really_connect_to(
    live_gateway: LiveGatewayFactory,
    fake_upstream: FakeUpstream,
    snapshot_builder: SnapshotBuilder,
    base_url: str,
) -> None:
    snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "svc", "/svc", strip_prefix=True, environments={EnvironmentName.STAGE: base_url}
    )
    gateway = live_gateway(snapshot_builder.build(), allowed_upstream_hosts=["allowed.test"])
    response = await gateway.client.get(f"/{SLUG}/svc/x")
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_unreachable"


@pytest.mark.req("PR-15")
async def test_wildcard_allowlist_entries_cover_subdomains_only(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer(SLUG)
    snapshot_builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        environments={EnvironmentName.STAGE: "http://dev.internal/"},  # the apex
    )
    gateway = live_gateway(snapshot_builder.build(), allowed_upstream_hosts=["*.dev.internal"])
    response = await gateway.client.get(f"/{SLUG}/svc/x")
    assert response.json()["code"] == "upstream_unreachable"


# ---- the proxy honours what was sent, as a whole ------------------------------------------------


@pytest.mark.req("PR-02")
async def test_the_small_body_echo_round_trips_through_the_proxy(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    body = await echo(gateway.client, "PUT", "/echo", content=b"\x00\x01binary\xff")
    assert base64.b64decode(body["body"]) == b"\x00\x01binary\xff"
