"""Admin writes reach a running Gateway within two seconds (PR-07, FR-08, PR-01).

Two real apps share one PostgreSQL: the Admin takes the request, the Gateway (with its real
SnapshotService, LISTEN connection and debounce) serves it. Nothing in between is mocked.
"""

import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.app import create_app
from mockan.gateway.app import create_app as create_gateway
from mockan.infrastructure.settings import MockanSettings
from tests.admin.builders import ME_RULES, create_rule, response_body
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import create_service
from tests.gateway.conftest import make_settings
from tests.gateway.test_snapshot_service import eventually
from tests.support.fake_upstream import UpstreamState, build_fake_upstream
from tests.support.live_server import LiveServer

pytestmark = [pytest.mark.db, pytest.mark.req("PR-07")]

TWO_SECONDS = 2.0


@pytest.fixture
def upstream() -> Iterator[LiveServer]:
    server = LiveServer(build_fake_upstream(UpstreamState()), lifespan="off").start()
    yield server
    server.stop()


@pytest.fixture
async def admin(
    admin_settings: MockanSettings,
    session_factory: async_sessionmaker[AsyncSession],
    upstream: LiveServer,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsDeveloper]]:
    settings = admin_settings.model_copy(update={"allowed_upstream_hosts": [upstream.host]})
    app = create_app(settings, session_factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://admin") as client:
        yield client, AsDeveloper(app, session_factory)


@dataclass
class Gateway:
    client: httpx.AsyncClient


@asynccontextmanager
async def running_gateway(
    database_url: str, *, allowed_upstream_hosts: list[str]
) -> AsyncIterator[Gateway]:
    """The real Gateway lifespan: shared upstream client, SnapshotService, LISTEN, debounce."""
    settings = make_settings(
        database_url=database_url,
        snapshot_debounce_ms=20,
        allowed_upstream_hosts=allowed_upstream_hosts,
    )
    app = create_gateway(settings)
    async with app.router.lifespan_context(app):
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        )

        async def ready() -> bool:
            return (await client.get("/_mockan/health/ready")).status_code == 200

        try:
            await eventually(ready, within=10)
            yield Gateway(client)
        finally:
            await client.aclose()


async def add_echo_service(client: httpx.AsyncClient, upstream: LiveServer) -> None:
    """Service `/echo` whose `stage` environment is the live fake upstream."""
    service = await create_service(client, name="echo", pathPrefix="/echo")
    created = await client.post(
        f"/api/v1/services/{service['id']}/environments",
        json={"environment": "stage", "baseUrl": upstream.url, "timeoutSeconds": 10},
    )
    assert created.status_code == 201, created.text


async def source(gateway: Gateway, path: str) -> str:
    return (await gateway.client.get(path)).headers["x-mockan-source"]


async def becomes(gateway: Gateway, path: str, expected: str) -> float:
    """Wait until `path` is answered with `X-Mockan-Source: expected`; returns the seconds taken."""

    async def check() -> bool:
        return await source(gateway, path) == expected

    return await eventually(check, within=TWO_SECONDS)


async def test_a_rule_saved_in_the_admin_is_served_by_the_gateway_within_two_seconds(
    admin: tuple[httpx.AsyncClient, AsDeveloper], pg_container: str, upstream: LiveServer
) -> None:
    client, as_developer = admin
    await as_developer("ehtesham", is_admin=True)
    assert (await client.put("/api/v1/me", json={"slug": "ehtesham"})).status_code == 200
    await add_echo_service(client, upstream)

    async with running_gateway(pg_container, allowed_upstream_hosts=[upstream.host]) as gateway:
        path = "/ehtesham/echo"
        assert await source(gateway, path) == "proxy"  # no rule yet: transparent proxy

        started = time.perf_counter()
        rule = await create_rule(
            client,
            matchType="Exact",
            pattern="/echo",
            method="GET",
            responses=[
                response_body(name="a", body='{"from":"a"}'),
                response_body(name="b", body='{"from":"b"}', statusCode=201),
            ],
        )
        await becomes(gateway, path, "mock")
        assert time.perf_counter() - started < TWO_SECONDS
        served = await gateway.client.get(path)
        assert served.json() == {"from": "a"}
        assert served.headers["x-mockan-rule-id"] == rule["id"]

        # Activating the other response: served within two seconds.
        second = rule["responses"][1]["id"]
        await client.post(f"{ME_RULES}/{rule['id']}/responses/{second}/activate")

        async def switched() -> bool:
            return (await gateway.client.get(path)).status_code == 201

        await eventually(switched, within=TWO_SECONDS)

        # Toggle off: transparently proxied again.
        await client.post(f"{ME_RULES}/{rule['id']}/toggle", json={"isEnabled": False})
        await becomes(gateway, path, "proxy")
        await client.post(f"{ME_RULES}/{rule['id']}/toggle", json={"isEnabled": True})
        await becomes(gateway, path, "mock")

        # Toggle-all is a bulk UPDATE: only an explicit `notify.mark` makes the Gateway see it.
        assert (await client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})).json() == {
            "updated": 1
        }
        await becomes(gateway, path, "proxy")
        await client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": True})
        await becomes(gateway, path, "mock")

        # Editing the pattern moves the mock; deleting the rule ends it.
        await client.put(
            f"{ME_RULES}/{rule['id']}",
            json={
                **{k: rule[k] for k in ("serviceId", "name", "method", "matchType", "priority")},
                "pattern": "/echo/elsewhere",
                "queryConditions": [],
                "headerConditions": [],
            },
        )
        await becomes(gateway, path, "proxy")
        await becomes(gateway, "/ehtesham/echo/elsewhere", "mock")
        await client.delete(f"{ME_RULES}/{rule['id']}")
        await becomes(gateway, "/ehtesham/echo/elsewhere", "proxy")


async def test_one_developers_rules_never_reach_another_developers_path(
    admin: tuple[httpx.AsyncClient, AsDeveloper], pg_container: str, upstream: LiveServer
) -> None:
    client, as_developer = admin
    alice = await as_developer("alice", is_admin=True)
    await client.put("/api/v1/me", json={"slug": "alice"})
    await add_echo_service(client, upstream)
    await create_rule(client, pattern="/echo", method="GET")
    await as_developer("bob")
    await client.put("/api/v1/me", json={"slug": "bob"})

    async with running_gateway(pg_container, allowed_upstream_hosts=[upstream.host]) as gateway:
        await becomes(gateway, "/alice/echo", "mock")
        assert await source(gateway, "/bob/echo") != "mock"  # PR-01

        as_developer.switch(alice)
        await client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})
        await becomes(gateway, "/alice/echo", "proxy")
