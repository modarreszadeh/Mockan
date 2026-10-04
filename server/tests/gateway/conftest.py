"""Fixtures for Gateway integration tests: the real ASGI app over an in-memory snapshot."""

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from mockan.gateway.app import create_app
from mockan.infrastructure.settings import MockanSettings
from mockan.matching.snapshot import RuleSnapshot, RuleSnapshotProvider

ClientFactory = Callable[..., httpx.AsyncClient]


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
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://gateway",
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()
