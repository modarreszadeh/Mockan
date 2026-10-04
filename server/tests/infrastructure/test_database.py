"""Schema, migration and model behaviour against a real PostgreSQL (needs Docker)."""

import uuid

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mockan.domain.enums import (
    AuditAction,
    AuditEntityType,
    BodyMode,
    EnvironmentName,
    MatchType,
)
from mockan.infrastructure import audit
from mockan.infrastructure.db.models import (
    AuditLog,
    Developer,
    DeveloperServiceSetting,
    MockResponse,
    MockRule,
    Service,
)
from tests.conftest import alembic_config
from tests.infrastructure.helpers import make_developer, make_rule, make_service

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


def test_migration_matches_the_models_and_alembic_check_shows_no_drift(pg_container: str) -> None:
    # `pg_container` already ran `upgrade head` on an empty database.
    command.check(alembic_config(pg_container))


def test_downgrade_then_upgrade_round_trips(pg_container: str) -> None:
    config = alembic_config(pg_container)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


async def _persist_rule(session: AsyncSession, rule: MockRule, *responses: MockResponse) -> None:
    session.add(rule)
    await session.flush()
    for response in responses:
        response.rule_id = rule.id
        session.add(response)
    await session.flush()
    rule.active_response_id = responses[0].id


async def test_a_full_graph_round_trips_with_defaults(session_factory: Factory) -> None:
    async with session_factory() as session:
        developer = make_developer()
        service = make_service()
        session.add_all([developer, service])
        await session.flush()
        rule, response = make_rule(developer, service_id=service.id)
        await _persist_rule(session, rule, response)
        env = service.environments[1]
        session.add(
            DeveloperServiceSetting(
                developer_id=developer.id, service_id=service.id, service_environment_id=env.id
            )
        )
        audit.record(
            session,
            developer,
            AuditAction.CREATE,
            AuditEntityType.MOCK_RULE,
            rule.id,
            {"name": "n"},
        )
        await session.commit()

    async with session_factory() as session:
        loaded = (await session.scalars(select(MockRule))).one()
        assert isinstance(loaded.id, uuid.UUID)
        assert loaded.id.version == 7
        assert loaded.created_at is not None
        assert loaded.updated_at is not None
        assert (loaded.method, loaded.priority, loaded.is_enabled) == ("ANY", 100, True)
        assert loaded.match_type is MatchType.EXACT
        assert loaded.query_conditions == []
        assert loaded.active_response_id == response.id
        saved = await session.get(MockResponse, response.id)
        assert saved is not None
        assert (saved.status_code, saved.headers, saved.body_mode) == (
            200,
            {"X-A": "1"},
            BodyMode.STATIC,
        )
        assert saved.content_type == "application/json"
        dev = await session.get(Developer, developer.id)
        assert dev is not None
        assert (dev.is_enabled, dev.is_admin) == (True, False)
        assert dev.allowed_origins == ["http://localhost:*"]
        svc = await session.get(Service, service.id)
        assert svc is not None
        assert svc.default_environment is EnvironmentName.STAGE
        assert (await session.scalars(select(AuditLog))).one().action is AuditAction.CREATE


async def test_updated_at_moves_on_update_without_lazy_loading(session_factory: Factory) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.commit()
        first = developer.updated_at
        developer.display_name = "Renamed"
        await session.commit()
        assert developer.updated_at > first  # eager_defaults: no hidden refresh needed


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO mockan.mock_rules (id, developer_id, name, match_type, pattern, method) "
        "SELECT gen_random_uuid(), id, 'x', 'Exact', '/a', 'FETCH' FROM mockan.developers",
        "INSERT INTO mockan.mock_rules (id, developer_id, name, match_type, pattern) "
        "SELECT gen_random_uuid(), id, 'x', 'Fuzzy', '/a' FROM mockan.developers",
        "INSERT INTO mockan.mock_rules (id, developer_id, name, match_type, pattern, priority) "
        "SELECT gen_random_uuid(), id, 'x', 'Exact', '/a', -1 FROM mockan.developers",
    ],
)
async def test_checks_reject_bad_rule_values(engine: AsyncEngine, statement: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO mockan.developers (id, display_name, sso_subject) "
                "VALUES (gen_random_uuid(), 'd', 's')"
            )
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(text(statement))


async def test_checks_reject_bad_response_values(session_factory: Factory) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()  # ids are assigned at flush
        rule, _ = make_rule(developer)
        session.add(rule)
        await session.commit()
        rule_id = rule.id  # a rollback expires loaded objects
        for kwargs in ({"status_code": 99}, {"status_code": 600}, {"delay_ms": 30_001}):
            session.add(MockResponse(rule_id=rule_id, name="r", **{"status_code": 200, **kwargs}))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()


async def test_unique_constraints(session_factory: Factory) -> None:
    async with session_factory() as session:
        session.add_all([make_developer("ann", sso_subject="s1"), make_service("a", "/a")])
        await session.commit()
        for duplicate in (
            make_developer("ann"),  # slug
            make_developer("bob", sso_subject="s1"),  # sso_subject
            make_service("a", "/other"),  # name
            make_service("b", "/a"),  # path_prefix
        ):
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()


async def test_many_developers_may_have_no_slug_yet(session_factory: Factory) -> None:
    async with session_factory() as session:
        session.add_all([make_developer(None), make_developer(None)])
        await session.commit()


async def test_one_environment_per_service_and_name(session_factory: Factory) -> None:
    from mockan.infrastructure.db.models import ServiceEnvironment

    async with session_factory() as session:
        service = make_service()
        session.add(service)
        await session.commit()
        session.add(
            ServiceEnvironment(
                service_id=service.id, environment=EnvironmentName.DEV, base_url="https://x"
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(text(f"SELECT count(*) FROM mockan.{table}")) or 0)


async def test_fk_delete_policy(engine: AsyncEngine, session_factory: Factory) -> None:
    async with session_factory() as session:
        developer = make_developer()
        service = make_service()
        session.add_all([developer, service])
        await session.flush()
        rule, response = make_rule(developer, service_id=service.id)
        await _persist_rule(session, rule, response)
        env = service.environments[0]
        session.add(
            DeveloperServiceSetting(
                developer_id=developer.id, service_id=service.id, service_environment_id=env.id
            )
        )
        audit.record(session, developer, AuditAction.CREATE, AuditEntityType.MOCK_RULE, rule.id)
        await session.commit()
        developer_id, service_id, rule_id, response_id = (
            developer.id,
            service.id,
            rule.id,
            response.id,
        )

    # services.* -> environments and settings CASCADE; mock_rules.service_id SET NULL
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM mockan.services WHERE id = :id"), {"id": service_id}
        )
    assert await _count(engine, "service_environments") == 0
    assert await _count(engine, "developer_service_settings") == 0
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT service_id FROM mockan.mock_rules WHERE id = :id"), {"id": rule_id}
            )
        ) is None

    # mock_rules.active_response_id SET NULL when the active response is deleted
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM mockan.mock_responses WHERE id = :id"), {"id": response_id}
        )
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT active_response_id FROM mockan.mock_rules WHERE id = :id"),
                {"id": rule_id},
            )
        ) is None

    # mock_rules.developer_id RESTRICT: a Developer with rules can't be deleted
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM mockan.developers WHERE id = :id"), {"id": developer_id}
            )

    # mock_responses.rule_id CASCADE with the rule; audit rows survive (no FK, keep history)
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM mockan.mock_rules WHERE id = :id"), {"id": rule_id}
        )
        await connection.execute(
            text("DELETE FROM mockan.developers WHERE id = :id"), {"id": developer_id}
        )
    assert await _count(engine, "mock_responses") == 0
    assert await _count(engine, "audit_logs") == 1


async def test_deleting_a_rule_cascades_to_its_responses(
    engine: AsyncEngine, session_factory: Factory
) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()
        rule, first = make_rule(developer)
        second = MockResponse(rule_id=rule.id, name="empty", status_code=204)
        await _persist_rule(session, rule, first, second)
        await session.commit()
        assert await _count(engine, "mock_responses") == 2
        await session.delete(rule)
        await session.commit()
    assert await _count(engine, "mock_responses") == 0


async def test_audit_changes_are_masked_in_the_same_transaction(
    engine: AsyncEngine, session_factory: Factory
) -> None:
    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()
        audit.record(
            session,
            developer,
            AuditAction.UPDATE,
            AuditEntityType.SERVICE_ENVIRONMENT,
            "env-1",
            {"extraHeaders": {"Authorization": "Bearer abc", "X-Team": "a"}, "name": "n"},
        )
        await session.rollback()  # rolled back with the change itself
    assert await _count(engine, "audit_logs") == 0

    async with session_factory() as session:
        developer = make_developer()
        session.add(developer)
        await session.flush()
        entry = audit.record(
            session,
            developer,
            AuditAction.UPDATE,
            AuditEntityType.SERVICE_ENVIRONMENT,
            "env-1",
            {"extraHeaders": {"Authorization": "Bearer abc", "X-Team": "a"}, "name": "n"},
        )
        audit.record(
            session, developer, AuditAction.DELETE, AuditEntityType.DEVELOPER, uuid.uuid7()
        )
        await session.commit()
        assert entry.changes == {
            "extraHeaders": {"Authorization": "***", "X-Team": "a"},
            "name": "n",
        }
    async with session_factory() as session:
        rows = (await session.scalars(select(AuditLog).order_by(AuditLog.id))).all()
        assert [r.developer_id for r in rows] == [developer.id, developer.id]
        assert rows[1].changes == {}
        assert rows[0].timestamp is not None
