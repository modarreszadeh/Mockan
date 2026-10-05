"""Fixtures for Gateway integration tests: the real ASGI app over an in-memory snapshot."""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI

from mockan.gateway.app import create_app
from mockan.infrastructure.settings import MockanSettings
from mockan.matching.snapshot import RuleSnapshot, RuleSnapshotProvider
from tests.support.fake_upstream import UpstreamState, build_fake_upstream
from tests.support.live_server import LiveServer

ClientFactory = Callable[..., httpx.AsyncClient]


class LifespanTransport(httpx.ASGITransport):
    """`ASGITransport` that also runs the app lifespan (shared upstream client), lazily."""

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app=app, raise_app_exceptions=False)
        self._lifespan = app.router.lifespan_context(app)
        self._started = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._started:
            await self._lifespan.__aenter__()
            self._started = True
        return await super().handle_async_request(request)

    async def aclose(self) -> None:
        if self._started:
            await self._lifespan.__aexit__(None, None, None)
        await super().aclose()


def make_settings(**overrides: object) -> MockanSettings:
    values: dict[str, object] = {
        "public_base_url": "https://mock.test",
        "default_allowed_origins": ["http://localhost:*"],
        "log_level": "WARNING",
    }
    return MockanSettings(_env_file=None, **{**values, **overrides})  # type: ignore[arg-type]


@pytest.fixture
async def gateway_client() -> AsyncIterator[ClientFactory]:
    """`gateway_client(snapshot)` -> an `httpx.AsyncClient` on the Gateway app (no database)."""
    clients: list[httpx.AsyncClient] = []

    def make(snapshot: RuleSnapshot | None = None, **settings: object) -> httpx.AsyncClient:
        provider = RuleSnapshotProvider(snapshot)
        app = create_app(make_settings(**settings), provider)
        client = httpx.AsyncClient(
            transport=LifespanTransport(app),
            base_url="http://gateway",
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


@dataclass
class FakeUpstream:
    """The session-wide upstream: a real Uvicorn server (`tests/support/fake_upstream.py`)."""

    server: LiveServer
    state: UpstreamState

    @property
    def url(self) -> str:
        return self.server.url

    @property
    def host(self) -> str:
        return self.server.host

    @property
    def ws_url(self) -> str:
        return self.server.ws_url


@pytest.fixture(scope="session")
def fake_upstream_server() -> Iterator[FakeUpstream]:
    state = UpstreamState()
    server = LiveServer(build_fake_upstream(state), lifespan="off").start()
    yield FakeUpstream(server, state)
    server.stop()


@pytest.fixture
def fake_upstream(fake_upstream_server: FakeUpstream) -> FakeUpstream:
    fake_upstream_server.state.reset()
    return fake_upstream_server


@dataclass
class LiveGateway:
    """The Gateway on a real socket, over a swappable in-memory snapshot."""

    server: LiveServer
    provider: RuleSnapshotProvider
    client: httpx.AsyncClient

    @property
    def url(self) -> str:
        return self.server.url

    @property
    def ws_url(self) -> str:
        return self.server.ws_url


LiveGatewayFactory = Callable[..., LiveGateway]


@pytest.fixture
async def live_gateway(fake_upstream: FakeUpstream) -> AsyncIterator[LiveGatewayFactory]:
    """`live_gateway(snapshot, **settings)` -> a Gateway on a real socket, upstream allowlisted."""
    started: list[LiveGateway] = []

    def make(snapshot: RuleSnapshot, **settings: object) -> LiveGateway:
        provider = RuleSnapshotProvider(snapshot)
        values: dict[str, object] = {"allowed_upstream_hosts": [fake_upstream.host], **settings}
        server = LiveServer(create_app(make_settings(**values), provider)).start()
        client = httpx.AsyncClient(base_url=server.url, trust_env=False, timeout=30)
        gateway = LiveGateway(server, provider, client)
        started.append(gateway)
        return gateway

    yield make
    for gateway in started:
        await gateway.client.aclose()
        gateway.server.stop()
