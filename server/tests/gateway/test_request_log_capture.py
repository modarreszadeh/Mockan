"""The Gateway offers one `LogEntry` per Developer request, no buffering (PR-12, D-18)."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest

from mockan.domain.constants import SAMPLE_BYTES
from mockan.domain.enums import MatchType, RequestSource
from mockan.gateway.app import create_app
from mockan.infrastructure.request_log import LogEntry, RequestLogQueue
from mockan.matching.snapshot import RuleSnapshotProvider
from tests.gateway.conftest import FakeUpstream, make_settings
from tests.support.live_server import LiveServer
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = [pytest.mark.asyncio, pytest.mark.req("PR-12")]


@dataclass
class Logged:
    client: httpx.AsyncClient
    queue: RequestLogQueue

    def entries(self) -> list[LogEntry]:
        found: list[LogEntry] = []
        while True:
            try:
                found.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                return found

    async def settled(self, count: int) -> list[LogEntry]:
        """The entry is offered when the response ends, a moment after the client has it."""
        for _ in range(200):
            if self.queue.qsize() >= count:
                break
            await asyncio.sleep(0.01)
        return self.entries()

    async def only(self) -> LogEntry:
        (entry,) = await self.settled(1)
        return entry


LoggedFactory = Callable[..., Logged]


@pytest.fixture
async def logged(fake_upstream: FakeUpstream) -> AsyncIterator[LoggedFactory]:
    """`logged(snapshot, **settings)`: a live Gateway whose request-log queue the test can read."""
    started: list[tuple[LiveServer, httpx.AsyncClient]] = []

    def make(snapshot_builder: SnapshotBuilder, **settings: object) -> Logged:
        provider = RuleSnapshotProvider(snapshot_builder.build())
        values: dict[str, object] = {"allowed_upstream_hosts": [fake_upstream.host], **settings}
        app = create_app(make_settings(**values), provider)
        server = LiveServer(app).start()
        client = httpx.AsyncClient(base_url=server.url, trust_env=False, timeout=30)
        started.append((server, client))
        return Logged(client, app.state.request_log)

    yield make
    for server, client in started:
        await client.aclose()
        server.stop()


def with_service(builder: SnapshotBuilder, upstream: FakeUpstream) -> tuple[uuid.UUID, uuid.UUID]:
    dev = builder.developer("ehtesham")
    service = builder.service("echo", "/echo", environments={"stage": upstream.url})  # type: ignore[dict-item]
    return dev.id, service.id


async def test_a_mocked_request_is_logged_with_what_the_panel_needs(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    rule = snapshot_builder.rule(dev, MatchType.EXACT, "/limsa/dash", body='{"ok":true}')
    gateway = logged(snapshot_builder)

    response = await gateway.client.get("/ehtesham/limsa/dash?page=2", headers={"x-a": "1"})

    entry = await gateway.only()
    assert response.headers["x-mockan-source"] == "mock"
    assert entry.developer_id == dev.id
    assert (entry.method, entry.path, entry.query) == ("GET", "/limsa/dash", "page=2")
    assert (entry.source, entry.status_code, entry.rule_id) == (RequestSource.MOCKED, 200, rule.id)
    assert entry.service_id is None
    assert entry.duration_ms >= 0
    assert (b"x-a", b"1") in list(entry.request_headers)
    assert (b"x-mockan-source", b"mock") in list(entry.response_headers)
    assert entry.response_sample == b'{"ok":true}'
    assert entry.timestamp.tzinfo is not None


async def test_a_proxied_request_is_logged_with_its_service_and_both_body_samples(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    dev_id, service_id = with_service(snapshot_builder, fake_upstream)
    gateway = logged(snapshot_builder)

    response = await gateway.client.post("/ehtesham/echo", content=b"hello upstream")

    entry = await gateway.only()
    assert response.headers["x-mockan-source"] == "proxy"
    assert (entry.developer_id, entry.service_id, entry.source) == (
        dev_id,
        service_id,
        RequestSource.PROXIED,
    )
    assert (entry.method, entry.path, entry.status_code) == ("POST", "/echo", 200)
    assert entry.request_sample == b"hello upstream"
    assert b'"method":"POST"' in entry.response_sample


async def test_mockan_errors_are_logged_as_errors(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham")
    gateway = logged(snapshot_builder)

    response = await gateway.client.get("/ehtesham/nothing/here")

    entry = await gateway.only()
    assert response.status_code == 502
    assert (entry.source, entry.status_code) == (RequestSource.ERROR, 502)
    assert b"service_not_resolved" in entry.response_sample


async def test_requests_without_a_developer_are_not_logged(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham", origins=("http://localhost:*",))
    gateway = logged(snapshot_builder)

    await gateway.client.get("/nobody/x")  # unknown slug
    await gateway.client.options(  # preflight: answered before resolution
        "/ehtesham/x",
        headers={"origin": "http://localhost:3000", "access-control-request-method": "GET"},
    )
    await gateway.client.get("/_mockan/health/live")

    await asyncio.sleep(0.2)  # long enough for an entry to have been offered
    assert gateway.entries() == []


async def test_body_samples_stop_at_16_kb_while_the_whole_body_streams(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    with_service(snapshot_builder, fake_upstream)
    snapshot_builder.service("download", "/download", environments={"stage": fake_upstream.url})  # type: ignore[dict-item]
    gateway = logged(snapshot_builder)

    async def upload() -> AsyncIterator[bytes]:
        for _ in range(32):
            yield b"u" * 65536

    sent = await gateway.client.post("/ehtesham/echo", content=upload())
    downloaded = await gateway.client.get("/ehtesham/download", params={"mb": 2})

    assert sent.json()["bodyLength"] == 32 * 65536  # the proxy still carried every byte
    assert len(downloaded.content) == 2 * 1024 * 1024
    upload_entry, download_entry = await gateway.settled(2)
    assert len(upload_entry.request_sample) == SAMPLE_BYTES
    assert len(download_entry.response_sample) == SAMPLE_BYTES


async def test_a_full_queue_drops_entries_and_counts_them_without_failing_requests(
    logged: LoggedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/")
    gateway = logged(snapshot_builder, request_log_queue_size=3)

    statuses = [(await gateway.client.get(f"/ehtesham/x{i}")).status_code for i in range(10)]

    assert statuses == [200] * 10
    assert gateway.queue.qsize() == 3
    assert gateway.queue.dropped == 7
