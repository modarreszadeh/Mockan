"""PR-02 acceptance: a Developer with no rules behaves exactly like talking to the upstream.

Each case runs twice, directly against the fake upstream and through the Gateway, and the answers
must match: status, body bytes and every header the proxy is not meant to change (arch §6.3).
"""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from tests.gateway.conftest import FakeUpstream, LiveGatewayFactory
from tests.gateway.test_proxy import SLUG, strip_snapshot
from tests.support.fake_upstream import CHUNK
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = pytest.mark.asyncio

# Headers a proxy changes by design: hop-by-hop, the ASGI server's own, and Mockan's.
EXPECTED_DIFFERENCES = frozenset(
    {
        "date",
        "server",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "transfer-encoding",
        "x-private",
        "x-mockan-source",
        "x-mockan-rule-id",
        "vary",
    }
)


@dataclass(frozen=True)
class Case:
    id: str
    method: str
    path: str
    kwargs: dict[str, Any] = field(default_factory=dict)


CASES = [
    Case("get-with-query", "GET", "/echo?a=1&b=%20x&flag&a=2"),
    Case("encoded-path", "GET", "/echo/a%2Fb/c%20d/%E2%9C%93?q=%C3%BC"),
    Case("post-json", "POST", "/echo", {"json": {"name": "ü", "items": [1, 2, 3]}}),
    Case("put-binary", "PUT", "/echo", {"content": bytes(range(256)) * 100}),
    Case("patch-text", "PATCH", "/echo/orders/42", {"content": "plain text"}),
    Case("delete", "DELETE", "/echo/orders/42"),
    Case("options", "OPTIONS", "/echo"),
    Case("authorization-header", "GET", "/echo", {"headers": {"authorization": "Bearer abc"}}),
    Case("head", "HEAD", "/echo"),
    Case("chunked-response", "GET", "/stream"),
    Case("gzip-body", "GET", "/gzip"),
    Case("download-1mb", "GET", "/download?mb=1"),
    Case("no-content", "GET", "/status/204"),
    Case("not-modified", "GET", "/status/304"),
    Case("not-found", "GET", "/status/404"),
    Case("server-error", "GET", "/status/500"),
    Case("cors-headers-upstream-owns", "GET", "/cors"),
    Case("plain-headers", "GET", "/response-headers"),
]


async def fetch(
    client: httpx.AsyncClient, case: Case, url: str
) -> tuple[int, httpx.Headers, bytes]:
    async with client.stream(case.method, url, **case.kwargs) as response:
        return (
            response.status_code,
            response.headers,
            b"".join([part async for part in response.aiter_raw()]),
        )


def normalised(case: Case, body: bytes) -> object:
    """The echo reports its own request headers, which a proxy legitimately changes."""
    if not case.path.startswith("/echo") or not body:
        return body
    echo = json.loads(body)
    return {key: echo[key] for key in ("method", "rawPath", "query", "bodyLength", "bodySha256")}


@pytest.mark.req("PR-02")
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
async def test_the_gateway_answers_like_the_upstream_for_a_developer_without_rules(
    live_gateway: LiveGatewayFactory,
    fake_upstream: FakeUpstream,
    snapshot_builder: SnapshotBuilder,
    case: Case,
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    direct_status, direct_headers, direct_body = await fetch(
        gateway.client, case, f"{fake_upstream.url}{case.path}"
    )
    via_status, via_headers, via_body = await fetch(gateway.client, case, f"/{SLUG}/svc{case.path}")

    assert via_status == direct_status
    assert normalised(case, via_body) == normalised(case, direct_body)

    for name in direct_headers:
        if name in EXPECTED_DIFFERENCES or name.startswith("access-control-"):
            continue
        if name == "content-length" and case.path.startswith("/echo"):
            continue  # the echoed headers differ in length, the payload fields above do not
        assert via_headers.get_list(name) == direct_headers.get_list(name), name

    added = set(via_headers) - set(direct_headers)
    assert added <= EXPECTED_DIFFERENCES | {"content-length"} | {
        name for name in added if name.startswith("access-control-")
    }
    assert via_headers["x-mockan-source"] == "proxy"


@pytest.mark.req("PR-02")
async def test_a_large_download_is_byte_identical(
    live_gateway: LiveGatewayFactory, fake_upstream: FakeUpstream, snapshot_builder: SnapshotBuilder
) -> None:
    gateway = live_gateway(strip_snapshot(snapshot_builder, fake_upstream))
    case = Case("download", "GET", "/download?mb=2")
    _, _, body = await fetch(gateway.client, case, f"/{SLUG}/svc{case.path}")
    assert body == CHUNK * 32
