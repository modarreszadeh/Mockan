"""`pg_notify('mockan_config_changed', …)` on commit, never on rollback (D-07, FR-08)."""

import asyncio
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from mockan.domain.enums import EnvironmentName
from mockan.infrastructure.db import notify
from mockan.infrastructure.db.models import (
    Developer,
    DeveloperServiceSetting,
    MockResponse,
    MockRule,
    Service,
)
from tests.infrastructure.helpers import make_developer, make_rule, make_service

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


class Listener:
    def __init__(self) -> None:
        self.received: list[str] = []

    def __call__(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        self.received.append(payload)

    async def payloads(self, expected: int) -> list[str]:
        """Wait (up to 3 s) for `expected` notifications, then pause briefly to catch extras."""
        for _ in range(60):
            if len(self.received) >= expected:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        result, self.received = sorted(self.received), []
        return result

    async def nothing(self) -> list[str]:
        await asyncio.sleep(0.4)
        result, self.received = sorted(self.received), []
        return result


@pytest.fixture
async def listener(pg_container: str, engine: object) -> AsyncIterator[Listener]:
    connection = await asyncpg.connect(pg_container.replace("+asyncpg", ""))
    listener = Listener()
    await connection.add_listener(notify.CHANNEL, listener)
    yield listener
    await connection.close()


async def _developer_with_rule(
    factory: Factory, listener: Listener
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()
        rule, response = make_rule(developer)
        session.add(rule)
        await session.flush()
        response.rule_id = rule.id
        session.add(response)
        await session.commit()
        ids = (developer.id, rule.id, response.id)
    await listener.payloads(1)  # drain
    return ids


async def test_committing_a_developer_notifies_with_its_id(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.commit()
    assert await listener.payloads(1) == [str(developer.id)]


async def test_a_rule_with_responses_and_a_setting_sends_one_payload_per_developer(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()
        rule, first = make_rule(developer)
        session.add(rule)
        await session.flush()
        first.rule_id = rule.id
        second = MockResponse(rule_id=rule.id, name="empty", status_code=204)
        session.add_all([first, second])
        await session.commit()
    assert await listener.payloads(1) == [str(developer.id)]


async def test_catalog_changes_notify_with_catalog(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        session.add(make_service())
        await session.commit()
    assert await listener.payloads(1) == [notify.CATALOG]

    async with session_factory() as session:
        loaded = (
            await session.scalars(select(Service).options(selectinload(Service.environments)))
        ).one()
        loaded.environments[0].base_url = "https://changed.internal"  # a ServiceEnvironment edit
        await session.commit()
    assert await listener.payloads(1) == [notify.CATALOG]


async def test_two_developers_in_one_commit_send_two_payloads(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        a, b = make_developer("alice"), make_developer("bob")
        session.add_all([a, b])
        await session.commit()
    assert await listener.payloads(2) == sorted([str(a.id), str(b.id)])


async def test_a_rollback_sends_nothing_and_leaves_no_stale_payload(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        session.add(make_developer("alice"))
        await session.flush()
        await session.rollback()
        # Same session, new transaction: only this commit may notify.
        other = make_developer("bob")
        session.add(other)
        await session.commit()
    assert await listener.payloads(1) == [str(other.id)]

    async with session_factory() as session:
        session.add(make_developer("carol"))
        await session.flush()
        await session.rollback()
    assert await listener.nothing() == []


async def test_a_failed_transaction_sends_nothing(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        session.add_all(
            [make_developer("dup", sso_subject="s"), make_developer("dup2", sso_subject="s")]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    assert await listener.nothing() == []


async def test_an_explicit_flush_before_commit_still_notifies(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()  # the session is clean by commit time
        await session.commit()
    assert await listener.payloads(1) == [str(developer.id)]


async def test_a_read_only_transaction_sends_nothing(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        await session.scalars(select(Developer))
        await session.commit()
    assert await listener.nothing() == []


async def test_changing_only_a_response_notifies_the_rules_developer(
    session_factory: Factory, listener: Listener
) -> None:
    developer_id, _, response_id = await _developer_with_rule(session_factory, listener)
    async with session_factory() as session:
        response = await session.get(MockResponse, response_id)
        assert response is not None
        response.status_code = 404
        await session.commit()
    assert await listener.payloads(1) == [str(developer_id)]


async def test_deleting_a_rule_notifies_its_developer(
    session_factory: Factory, listener: Listener
) -> None:
    developer_id, rule_id, _ = await _developer_with_rule(session_factory, listener)
    async with session_factory() as session:
        rule = await session.get(MockRule, rule_id)
        assert rule is not None
        await session.delete(rule)
        await session.commit()
    assert await listener.payloads(1) == [str(developer_id)]


async def test_bulk_updates_bypass_the_orm_and_notify_only_when_marked(
    session_factory: Factory, listener: Listener
) -> None:
    developer_id, _, _ = await _developer_with_rule(session_factory, listener)
    async with session_factory() as session:
        await session.execute(
            update(MockRule).where(MockRule.developer_id == developer_id).values(is_enabled=False)
        )
        await session.commit()
    assert await listener.nothing() == []

    async with session_factory() as session:
        await session.execute(
            update(MockRule).where(MockRule.developer_id == developer_id).values(is_enabled=True)
        )
        notify.mark(session, developer_id)
        notify.mark(session, developer_id)
        notify.mark(session, "catalog")
        await session.commit()
    assert await listener.payloads(2) == sorted([str(developer_id), notify.CATALOG])


async def test_environment_and_setting_changes_are_attributed(
    session_factory: Factory, listener: Listener
) -> None:
    async with session_factory() as session:
        developer, service = make_developer(), make_service()
        session.add_all([developer, service])
        await session.commit()
    await listener.payloads(2)
    async with session_factory() as session:
        env = service.environments[0]
        assert env.environment is EnvironmentName.DEV
        session.add(
            DeveloperServiceSetting(
                developer_id=developer.id, service_id=service.id, service_environment_id=env.id
            )
        )
        await session.commit()
    assert await listener.payloads(1) == [str(developer.id)]
