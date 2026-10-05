"""DB rows -> compiled `RuleSnapshot` (D-07). Needs Docker."""

import uuid

import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import EnvironmentName, MatchType
from mockan.infrastructure.db.models import DeveloperServiceSetting, MockResponse, MockRule
from mockan.infrastructure.snapshot_loader import load_developer, load_full, load_services
from mockan.matching.matcher import match_request
from mockan.matching.service_resolver import resolve_service
from tests.infrastructure.helpers import make_developer, make_rule, make_service
from tests.support.snapshot_builder import facts

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


async def _add_rule(
    session: AsyncSession, developer_id: uuid.UUID, pattern: str, **overrides: object
) -> MockRule:
    match_type = overrides.pop("match_type", MatchType.EXACT)
    with_response = overrides.pop("with_response", True)
    rule = MockRule(
        developer_id=developer_id,
        name=f"rule {pattern}",
        match_type=match_type,
        pattern=pattern,
        **overrides,
    )
    session.add(rule)
    await session.flush()
    if with_response:
        response = MockResponse(
            rule_id=rule.id,
            name="ok",
            status_code=201,
            headers={"X-A": "1"},
            body='{"a":1}',
            delay_ms=5,
        )
        session.add(response)
        await session.flush()
        rule.active_response_id = response.id
    return rule


async def test_load_full_builds_developers_rules_and_services(session_factory: Factory) -> None:
    async with session_factory() as session:
        alice = make_developer("alice", allowed_origins=["http://localhost:*", "https://x.test"])
        session.add_all([alice, make_service("limsa", "/limsa"), make_service("portal", "/portal")])
        await session.flush()
        service = make_service("identity", "/identity")
        session.add(service)
        await session.flush()
        dev_env = next(e for e in service.environments if e.environment is EnvironmentName.DEV)
        session.add(
            DeveloperServiceSetting(
                developer_id=alice.id, service_id=service.id, service_environment_id=dev_env.id
            )
        )
        await _add_rule(
            session,
            alice.id,
            "/limsa/orders/{id}",
            match_type=MatchType.TEMPLATE,
            method="GET",
            priority=5,
            query_conditions=[{"key": "page", "operator": "equals", "value": "2"}],
            header_conditions=[{"key": "X-Env", "operator": "exists"}],
        )
        await session.commit()
        alice_id = alice.id

    async with session_factory() as session:
        snapshot = await load_full(session)

    developer = snapshot.developer_for_slug("alice")
    assert developer is not None
    assert developer.id == alice_id
    assert developer.allowed_origins == ("http://localhost:*", "https://x.test")
    assert developer.is_enabled
    assert [s.name for s in snapshot.services_sorted_by_prefix_len] == [
        "identity",
        "portal",
        "limsa",
    ]  # longest path prefix first
    resolved = resolve_service(snapshot, developer, "/identity/connect/token")
    assert resolved.environment.environment is EnvironmentName.DEV  # the Developer's setting
    assert resolve_service(snapshot, developer, "/limsa/x").environment.base_url == (
        "https://limsa.stage.internal"
    )

    (rule,) = snapshot.rules_for(alice_id)
    assert (rule.method, rule.priority, rule.match_type) == ("GET", 5, MatchType.TEMPLATE)
    assert rule.header_conditions[0].key == "x-env"  # compiled: names lower-cased
    assert rule.active_response is not None
    assert (rule.active_response.status_code, rule.active_response.delay_ms) == (201, 5)
    assert rule.active_response.body_bytes == b'{"a":1}'
    result = match_request(
        snapshot.rules_for(alice_id),
        facts("/limsa/orders/9", query={"page": ["2"]}, headers={"x-env": "dev"}),
    )
    assert result is not None
    assert result.params == {"id": "9"}


async def test_disabled_rules_disabled_developers_and_slugless_developers_are_left_out(
    session_factory: Factory,
) -> None:
    async with session_factory() as session:
        alice = make_developer("alice")
        bob = make_developer("bob", is_enabled=False)
        carol = make_developer(None)
        session.add_all([alice, bob, carol])
        await session.flush()
        await _add_rule(session, alice.id, "/on")
        await _add_rule(session, alice.id, "/off", is_enabled=False)
        await _add_rule(session, bob.id, "/bobs")
        await _add_rule(session, carol.id, "/carols")
        await session.commit()
        alice_id, bob_id, carol_id = alice.id, bob.id, carol.id

    async with session_factory() as session:
        snapshot = await load_full(session)

    assert sorted(snapshot.developers_by_slug) == ["alice", "bob"]
    bob_entry = snapshot.developer_for_slug("bob")
    assert bob_entry is not None
    assert bob_entry.is_enabled is False  # kept, so the Gateway can answer 404 and CORS can resolve
    assert [r.pattern for r in snapshot.rules_for(alice_id)] == ["/on"]
    assert snapshot.rules_for(bob_id) == ()
    assert snapshot.rules_for(carol_id) == ()


async def test_a_rule_that_cannot_compile_is_skipped_and_logged(session_factory: Factory) -> None:
    async with session_factory() as session:
        alice = make_developer("alice")
        session.add(alice)
        await session.flush()
        await _add_rule(session, alice.id, "/good")
        await _add_rule(
            session, alice.id, "(unclosed", match_type=MatchType.REGEX
        )  # bad manual edit
        await _add_rule(
            session, alice.id, "/bad-condition", query_conditions=[{"operator": "equals"}]
        )
        await _add_rule(
            session,
            alice.id,
            "/bad-operator",
            header_conditions=[{"key": "a", "operator": "contains", "value": "b"}],
        )
        await _add_rule(session, alice.id, "/no-response", with_response=False)
        await session.commit()
        alice_id = alice.id

    async with session_factory() as session:
        with structlog.testing.capture_logs() as logs:
            snapshot = await load_full(session)

    assert [r.pattern for r in snapshot.rules_for(alice_id)] == ["/good"]
    skipped = [entry for entry in logs if entry["event"] == "rule_skipped"]
    assert len(skipped) == 4
    assert {entry["developer_id"] for entry in skipped} == {str(alice_id)}
    assert "no active response" in {entry["reason"] for entry in skipped}


async def test_load_developer_returns_one_slice_that_merges_into_a_snapshot(
    session_factory: Factory,
) -> None:
    async with session_factory() as session:
        alice, bob = make_developer("alice"), make_developer("bob")
        disabled, slugless = make_developer("dis", is_enabled=False), make_developer(None)
        session.add_all([alice, bob, disabled, slugless])
        await session.flush()
        await _add_rule(session, alice.id, "/a")
        await _add_rule(session, bob.id, "/b")
        await _add_rule(session, disabled.id, "/d")
        await session.commit()
        ids = {"alice": alice.id, "bob": bob.id, "dis": disabled.id, "none": slugless.id}

    async with session_factory() as session:
        before = await load_full(session)
        # Change alice's rules, then rebuild only her slice.
        await _add_rule(session, ids["alice"], "/a2")
        await session.commit()
        alice_slice = await load_developer(session, ids["alice"])
        disabled_slice = await load_developer(session, ids["dis"])
        slugless_slice = await load_developer(session, ids["none"])
        missing_slice = await load_developer(session, uuid.uuid7())

    assert alice_slice.developer is not None
    assert sorted(r.pattern for r in alice_slice.rules) == ["/a", "/a2"]
    assert disabled_slice.developer is not None
    assert disabled_slice.developer.is_enabled is False
    assert disabled_slice.rules == ()
    assert (slugless_slice.developer, slugless_slice.rules) == (None, ())
    assert (missing_slice.developer, missing_slice.rules) == (None, ())

    after = before.with_developer_slice(
        ids["alice"], developer=alice_slice.developer, rules=alice_slice.rules
    )
    assert sorted(r.pattern for r in after.rules_for(ids["alice"])) == ["/a", "/a2"]
    assert after.rules_for(ids["bob"]) is before.rules_for(ids["bob"])  # untouched, shared


async def test_load_developer_reads_fresh_rows_not_a_stale_identity_map(
    session_factory: Factory,
) -> None:
    async with session_factory() as session:
        alice = make_developer("alice")
        session.add(alice)
        await session.flush()
        rule, response = make_rule(alice)
        session.add(rule)
        await session.flush()
        response.rule_id = rule.id
        session.add(response)
        await session.flush()
        rule.active_response_id = response.id
        await session.commit()

        first = await load_developer(session, alice.id)
        assert first.rules[0].active_response is not None
        assert first.rules[0].active_response.status_code == 200
        # Another session changes the response; the long-lived session must still see it.
        async with session_factory() as other:
            changed = await other.get(MockResponse, response.id)
            assert changed is not None
            changed.status_code = 418
            await other.commit()
        second = await load_developer(session, alice.id)
        assert second.rules[0].active_response is not None
        assert second.rules[0].active_response.status_code == 418


async def test_load_services_includes_environments(session_factory: Factory) -> None:
    async with session_factory() as session:
        session.add(make_service("limsa", "/limsa"))
        await session.commit()
    async with session_factory() as session:
        (service,) = await load_services(session)
    assert service.default_environment is EnvironmentName.STAGE
    assert set(service.environments) == {EnvironmentName.DEV, EnvironmentName.STAGE}
    assert service.environments[EnvironmentName.DEV].timeout_seconds == 100
    assert service.environments[EnvironmentName.DEV].extra_headers == {}
