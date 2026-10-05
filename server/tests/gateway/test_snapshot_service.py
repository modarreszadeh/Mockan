"""LISTEN/NOTIFY hot reload, degraded mode and recovery against real PostgreSQL (PR-07, FR-08)."""

import asyncio
import socket
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from alembic import command
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from mockan.domain.enums import MatchType
from mockan.gateway.app import create_app
from mockan.gateway.snapshot_service import LISTENER_APPLICATION_NAME, SnapshotService
from mockan.infrastructure.db.models import MockRule
from mockan.infrastructure.db.session import create_session_factory
from mockan.matching.snapshot import RuleSnapshotProvider
from tests.conftest import alembic_config
from tests.gateway.conftest import make_settings
from tests.infrastructure.helpers import make_developer, make_rule, make_service

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


async def eventually(
    check: Callable[[], Awaitable[bool]], *, within: float = 2.0, interval: float = 0.02
) -> float:
    """Poll `check` until it is true; returns the elapsed seconds or fails the test."""
    started = time.perf_counter()
    while time.perf_counter() - started < within:
        if await check():
            return time.perf_counter() - started
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {within}s")


@dataclass
class _Owner:  # just enough of a Developer for `make_rule`
    id: uuid.UUID


async def add_rule(
    factory: Factory,
    slug: str,
    pattern: str,
    *,
    body: str = '{"ok":true}',
    developer_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert (a Developer, if needed, and) a rule with one active response, like the Admin does."""
    async with factory() as session:
        if developer_id is None:
            developer = make_developer(slug)
            session.add(developer)
            await session.flush()
            developer_id = developer.id
        rule, response = make_rule(_Owner(developer_id), pattern, match_type=MatchType.EXACT)  # type: ignore[arg-type]
        response.body = body
        session.add(rule)
        await session.flush()
        response.rule_id = rule.id
        session.add(response)
        await session.flush()
        rule.active_response_id = response.id
        await session.commit()
        return developer_id, rule.id


@dataclass
class Running:
    client: httpx.AsyncClient
    service: SnapshotService
    provider: RuleSnapshotProvider
    factory: Factory
    engine: AsyncEngine

    async def is_mocked(self, path: str) -> bool:
        response = await self.client.get(path)
        return response.headers["x-mockan-source"] == "mock"


@asynccontextmanager
async def running_gateway(
    database_url: str, *, backoff_initial: float = 0.5, **settings: object
) -> AsyncIterator[Running]:
    engine = create_async_engine(database_url)
    factory = create_session_factory(engine)
    config = make_settings(**{"database_url": database_url, "snapshot_debounce_ms": 20, **settings})
    provider = RuleSnapshotProvider()
    service = SnapshotService(
        config, provider, factory, backoff_initial=backoff_initial, backoff_max=1.0
    )
    app = create_app(config, provider)
    app.state.snapshot_service = service
    await service.start()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")
    try:
        await eventually(lambda: _loaded_and_listening(provider, service), within=10)
        yield Running(client, service, provider, factory, engine)
    finally:
        await client.aclose()
        await service.stop()
        await engine.dispose()


async def _loaded_and_listening(provider: RuleSnapshotProvider, service: SnapshotService) -> bool:
    return provider.loaded and not service.degraded


@pytest.mark.req("PR-07")
async def test_a_rule_inserted_through_the_orm_is_served_within_two_seconds_and_toggling_it_off_too(
    pg_container: str, session_factory: Factory
) -> None:
    # The B3 exit, through the real lifespan: a mock served end to end from a row in Postgres.
    app = create_app(make_settings(database_url=pg_container, snapshot_debounce_ms=20))
    async with app.router.lifespan_context(app):
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        )
        await eventually(
            lambda: _ready(client), within=10
        )  # first snapshot loaded (503 starting -> 200)

        started = time.perf_counter()
        developer_id, rule_id = await add_rule(
            session_factory, "ehtesham", "/limsa/api/v1/dashboard"
        )

        async def mocked() -> bool:
            r = await client.get("/ehtesham/limsa/api/v1/dashboard")
            return r.headers["x-mockan-source"] == "mock"

        await eventually(mocked, within=2)
        assert time.perf_counter() - started < 2
        response = await client.get("/ehtesham/limsa/api/v1/dashboard")
        assert response.json() == {"ok": True}
        assert response.headers["x-mockan-rule-id"] == str(rule_id)

        async with session_factory() as session:  # toggle off, like Admin's toggle endpoint
            rule = await session.get(MockRule, rule_id)
            assert rule is not None
            rule.is_enabled = False
            await session.commit()

        async def not_mocked() -> bool:
            r = await client.get("/ehtesham/limsa/api/v1/dashboard")
            return r.headers["x-mockan-source"] != "mock"

        await eventually(not_mocked, within=2)

        # PR-01: the Developer id is stable while their rules change
        assert developer_id is not None
        await client.aclose()


async def _ready(client: httpx.AsyncClient) -> bool:
    return (await client.get("/_mockan/health/ready")).status_code == 200


@pytest.mark.req("PR-07")
async def test_a_change_to_one_developer_leaves_other_developers_rules_untouched(
    pg_container: str, session_factory: Factory
) -> None:
    async with running_gateway(pg_container) as gw:
        a_id, _ = await add_rule(session_factory, "alice", "/a")
        b_id, _ = await add_rule(session_factory, "bob", "/b")
        await eventually(lambda: gw.is_mocked("/bob/b"))
        await eventually(lambda: gw.is_mocked("/alice/a"))
        bob_rules = gw.provider.current.rules_for(b_id)

        await add_rule(session_factory, "alice", "/a2", developer_id=a_id)
        await eventually(lambda: gw.is_mocked("/alice/a2"))
        assert gw.provider.current.rules_for(b_id) is bob_rules  # slice rebuild shared bob's rules


@pytest.mark.req("FR-04")
async def test_a_catalog_change_triggers_a_full_reload(
    pg_container: str, session_factory: Factory
) -> None:
    async with running_gateway(pg_container) as gw:
        assert gw.provider.current.services_sorted_by_prefix_len == ()
        async with session_factory() as session:
            session.add(make_service("limsa", "/limsa"))
            await session.commit()

        async def has_service() -> bool:
            return len(gw.provider.current.services_sorted_by_prefix_len) == 1

        await eventually(has_service)


@pytest.mark.req("PR-07")
async def test_a_burst_of_commits_is_debounced_into_few_reloads(
    pg_container: str, session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with running_gateway(pg_container, snapshot_debounce_ms=150) as gw:
        developer_id, _ = await add_rule(session_factory, "ehtesham", "/r0")
        await eventually(lambda: gw.is_mocked("/ehtesham/r0"))
        calls: list[set[str]] = []
        original = gw.service._apply

        async def counting(pending: set[str]) -> None:
            calls.append(set(pending))
            await original(pending)

        monkeypatch.setattr(gw.service, "_apply", counting)
        for index in range(1, 11):
            await add_rule(session_factory, "ehtesham", f"/r{index}", developer_id=developer_id)
        await eventually(lambda: gw.is_mocked("/ehtesham/r10"))
        assert len(calls) <= 4  # 10 commits, a handful of reloads
        assert all(payload == {str(developer_id)} for payload in calls)


@pytest.mark.req("FR-08")
async def test_the_periodic_full_reload_is_the_safety_net_for_a_missed_notification(
    pg_container: str, session_factory: Factory
) -> None:
    async with running_gateway(pg_container, snapshot_reload_seconds=1) as gw:
        _, rule_id = await add_rule(session_factory, "ehtesham", "/quiet")
        await eventually(lambda: gw.is_mocked("/ehtesham/quiet"))
        # A raw bulk UPDATE sends no NOTIFY (the Admin must `notify.mark`); only the reload sees it.
        async with gw.engine.begin() as connection:
            await connection.execute(
                update(MockRule).where(MockRule.id == rule_id).values(is_enabled=False)
            )
        await eventually(lambda: _not_mocked(gw, "/ehtesham/quiet"), within=4)


async def _not_mocked(gw: Running, path: str) -> bool:
    return not await gw.is_mocked(path)


@pytest.mark.req("FR-08")
async def test_a_dropped_listener_reconnects_and_reloads_what_it_missed(
    pg_container: str, session_factory: Factory
) -> None:
    async with running_gateway(pg_container, backoff_initial=0.6) as gw:
        _, rule_id = await add_rule(session_factory, "ehtesham", "/missed")
        await eventually(lambda: gw.is_mocked("/ehtesham/missed"))

        async with gw.engine.begin() as connection:  # drop the LISTEN connection
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE application_name = :n"
                ),
                {"n": LISTENER_APPLICATION_NAME},
            )
            await connection.execute(
                update(MockRule).where(MockRule.id == rule_id).values(is_enabled=False)
            )

        await eventually(lambda: _is_degraded(gw), within=2)
        assert gw.provider.loaded  # still serving the last snapshot while disconnected
        assert await gw.is_mocked("/ehtesham/missed")  # stale but available (PR-07)
        # Reconnecting triggers a full reload, so the change nobody was notified about arrives.
        await eventually(lambda: _not_mocked(gw, "/ehtesham/missed"), within=6)
        await eventually(lambda: _loaded_and_listening(gw.provider, gw.service), within=6)


async def _is_degraded(gw: Running) -> bool:
    return gw.service.degraded


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.req("PR-07")
async def test_database_down_keeps_serving_and_reports_degraded_then_recovers() -> None:
    port = _free_port()
    with PostgresContainer("postgres:18", driver="asyncpg").with_bind_ports(
        5432, port
    ) as container:
        url = container.get_connection_url()
        await asyncio.to_thread(command.upgrade, alembic_config(url), "head")
        engine = create_async_engine(url, pool_pre_ping=True)  # survives the restart below
        factory = create_session_factory(engine)
        await add_rule(factory, "ehtesham", "/limsa/x")
        docker = container.get_wrapped_container()

        async with running_gateway(url, backoff_initial=0.2) as gw:
            await eventually(lambda: gw.is_mocked("/ehtesham/limsa/x"))
            assert (await gw.client.get("/_mockan/health/ready")).json()["status"] == "ready"

            await asyncio.to_thread(docker.stop, timeout=5)  # the database goes away
            await eventually(lambda: _is_degraded(gw), within=15)
            ready = await gw.client.get("/_mockan/health/ready")
            assert (
                ready.status_code == 200
            )  # stays in rotation: it still serves the last good rules
            assert ready.json()["status"] == "degraded"
            assert await gw.is_mocked("/ehtesham/limsa/x")  # mocks keep working with no database
            assert (await gw.client.get("/ehtesham/limsa/x")).json() == {"ok": True}

            await asyncio.to_thread(docker.start)  # the database comes back
            await eventually(lambda: _loaded_and_listening(gw.provider, gw.service), within=40)
            assert (await gw.client.get("/_mockan/health/ready")).json()["status"] == "ready"

            await add_rule(factory, "ehtesham", "/limsa/after", developer_id=_developer_id(gw))
            await eventually(lambda: gw.is_mocked("/ehtesham/limsa/after"), within=5)
        await engine.dispose()


def _developer_id(gw: Running) -> uuid.UUID:
    developer = gw.provider.current.developer_for_slug("ehtesham")
    assert developer is not None
    return developer.id
