"""`/me/rules`: CRUD, validation with the Gateway's own compiler, toggles (PR-05, PR-08, FR-11)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog, MockResponse, MockRule
from mockan.infrastructure.snapshot_loader import load_full
from tests.admin.builders import ME_RULES, create_rule, response_body, rule_body, update_body
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import SERVICE, create_service
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-05")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]


# ---- create and read ----


async def test_creating_a_rule_returns_the_panel_contract_and_activates_the_first_response(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    developer = await as_developer("ehtesham")

    response = await admin_client.post(
        ME_RULES,
        json=rule_body(
            responses=[response_body(name="ok"), response_body(name="boom", statusCode=500)]
        ),
    )

    assert response.status_code == 201
    rule = response.json()
    assert set(rule) == {
        "id",
        "developerId",
        "serviceId",
        "name",
        "method",
        "matchType",
        "pattern",
        "queryConditions",
        "headerConditions",
        "priority",
        "isEnabled",
        "activeResponseId",
        "responses",
        "createdAt",
        "updatedAt",
    }
    assert rule["developerId"] == str(developer.id)
    assert rule["isEnabled"] is True
    assert [r["name"] for r in rule["responses"]] == ["ok", "boom"]
    assert rule["activeResponseId"] == rule["responses"][0]["id"]
    assert set(rule["responses"][0]) == {
        "id",
        "ruleId",
        "name",
        "statusCode",
        "headers",
        "contentType",
        "body",
        "bodyMode",
        "delayMs",
        "createdAt",
        "updatedAt",
    }
    assert rule["responses"][0]["ruleId"] == rule["id"]
    assert rule["responses"][0]["bodyMode"] == "Static"
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json() == rule


async def test_a_rule_can_start_disabled_and_defaults_apply(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(
        ME_RULES,
        json={
            "name": "Minimal",
            "matchType": "Prefix",
            "pattern": "/x",
            "isEnabled": False,
            "responses": [{"name": "r", "statusCode": 204}],
        },
    )

    rule = response.json()
    assert response.status_code == 201
    assert (rule["method"], rule["priority"], rule["isEnabled"]) == ("ANY", 100, False)
    assert (rule["serviceId"], rule["queryConditions"], rule["headerConditions"]) == (None, [], [])
    assert rule["responses"][0]["contentType"] == "application/json"
    assert (rule["responses"][0]["body"], rule["responses"][0]["delayMs"]) == ("", 0)
    assert rule["responses"][0]["headers"] == {}


async def test_conditions_are_stored_normalised_and_exists_has_no_value(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    rule = await create_rule(
        admin_client,
        queryConditions=[
            {"key": " page ", "operator": "equals", "value": "2"},
            {"key": "debug", "operator": "exists", "value": "ignored"},
        ],
        headerConditions=[{"key": "X-Tenant", "operator": "equals", "value": ""}],
    )

    assert rule["queryConditions"] == [
        {"key": "page", "operator": "equals", "value": "2"},
        {"key": "debug", "operator": "exists"},  # no `value` at all, not null
    ]
    assert rule["headerConditions"] == [{"key": "X-Tenant", "operator": "equals", "value": ""}]


async def test_creating_a_rule_audits_without_bodies_and_masks_headers(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    await listener.payloads(1)

    rule = await create_rule(
        admin_client,
        responses=[
            response_body(
                headers={"Authorization": "Bearer hunter2", "X-Team": "core"},
                body='{"token":"s3cret"}',
            )
        ],
    )

    (entry,) = await audit_rows()
    assert (entry.action, entry.entity_type) == (AuditAction.CREATE, AuditEntityType.MOCK_RULE)
    assert entry.entity_id == rule["id"]
    assert entry.developer_id == developer.id
    assert entry.changes["pattern"] == "/limsa/api/v1/dashboard"
    (logged,) = entry.changes["responses"]
    assert logged["headers"] == {"Authorization": "***", "X-Team": "core"}
    assert logged["bodyBytes"] == len('{"token":"s3cret"}')
    assert "body" not in logged
    assert "s3cret" not in str(entry.changes)
    assert "hunter2" not in str(entry.changes)
    assert set(await listener.payloads(1)) == {str(developer.id)}


async def test_the_list_is_in_creation_order_and_only_mine(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    first = await create_rule(admin_client, name="first")
    second = await create_rule(admin_client, name="second", pattern="/other")
    await as_developer("bob")
    await create_rule(admin_client, name="bobs")

    as_developer.switch(alice)
    listed = (await admin_client.get(ME_RULES)).json()

    assert [r["id"] for r in listed] == [first["id"], second["id"]]
    assert all(r["responses"] for r in listed)


async def test_an_empty_list_for_a_new_developer(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    assert (await admin_client.get(ME_RULES)).json() == []


# ---- isolation (PR-01) ----


@pytest.mark.req("PR-01")
async def test_another_developers_rule_is_a_404_on_every_route(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    rule = await create_rule(admin_client)
    response_id = rule["responses"][0]["id"]
    await as_developer("bob")
    base = f"{ME_RULES}/{rule['id']}"

    calls = [
        ("GET", base, None),
        ("PUT", base, update_body(rule)),
        ("DELETE", base, None),
        ("POST", f"{base}/toggle", {"isEnabled": False}),
        ("POST", f"{base}/responses", response_body()),
        ("PUT", f"{base}/responses/{response_id}", response_body()),
        ("DELETE", f"{base}/responses/{response_id}", None),
        ("POST", f"{base}/responses/{response_id}/activate", None),
    ]
    for method, path, body in calls:
        response = await admin_client.request(method, path, json=body)
        assert response.status_code == 404, (method, path)
        assert response.json()["code"] == "not_found"

    as_developer.switch(alice)  # nothing of alice's changed
    assert (await admin_client.get(f"{base}")).json() == rule


@pytest.mark.req("PR-01")
async def test_a_foreign_id_looks_exactly_like_a_missing_one(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("alice")
    rule = await create_rule(admin_client)
    await as_developer("bob")

    foreign = await admin_client.get(f"{ME_RULES}/{rule['id']}")
    missing = await admin_client.get(f"{ME_RULES}/{uuid.uuid4()}")

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


async def test_the_rules_need_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get(ME_RULES)).status_code == 401
    assert (await admin_client.post(ME_RULES, json=rule_body())).status_code == 401
    assert (
        await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": True})
    ).status_code == 401


async def test_a_disabled_developer_can_list_but_not_write(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    assert (await admin_client.get(ME_RULES)).status_code == 200
    for method, path, body in [
        ("POST", ME_RULES, rule_body()),
        ("POST", f"{ME_RULES}/toggle-all", {"isEnabled": False}),
        ("PUT", f"{ME_RULES}/{uuid.uuid4()}", update_body(rule_body())),
        ("DELETE", f"{ME_RULES}/{uuid.uuid4()}", None),
    ]:
        response = await admin_client.request(method, path, json=body)
        assert response.status_code == 403, (method, path)
        assert response.json()["code"] == "developer_disabled"


# ---- validation ----


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"matchType": "Exact", "pattern": "no-slash"}, "pattern", "Start the pattern with “/”."),
        ({"pattern": ""}, "pattern", "Enter a pattern."),
        ({"pattern": "   "}, "pattern", "Enter a pattern."),
        ({"pattern": "/has space"}, "pattern", "Patterns can't contain spaces."),
        (
            {"matchType": "Prefix", "pattern": "/a/{id}"},
            "pattern",
            "Prefix patterns can't contain { or }. Use Template for parameters.",
        ),
        (
            {"matchType": "Template", "pattern": "/a/{*rest}/b"},
            "pattern",
            "{*name} can only be the last segment.",
        ),
        (
            {"matchType": "Template", "pattern": "/a/{id}/{id}"},
            "pattern",
            "Parameter {id} is used twice.",
        ),
        (
            {"matchType": "Regex", "pattern": "^/a(?=b)"},
            "pattern",
            "RE2 doesn't support lookahead or lookbehind.",
        ),
        (
            {"matchType": "Regex", "pattern": r"^/(a)\1"},
            "pattern",
            "RE2 doesn't support backreferences.",
        ),
        (
            {"matchType": "Regex", "pattern": "^/" + "a" * 511},
            "pattern",
            "Regex patterns can be at most 512 characters.",
        ),
        ({"matchType": "Regex", "pattern": "^/(unclosed"}, "pattern", None),
        (
            {"queryConditions": [{"key": " ", "operator": "exists"}]},
            "queryConditions.0.key",
            "Enter a name.",
        ),
        (
            {"headerConditions": [{"key": "X-A", "operator": "equals"}]},
            "headerConditions.0.value",
            "Enter a value.",
        ),
        (
            {
                "queryConditions": [
                    {"key": "a", "operator": "exists"},
                    {"key": "", "operator": "exists"},
                ]
            },
            "queryConditions.1.key",
            "Enter a name.",
        ),
    ],
)
async def test_invalid_patterns_and_conditions_use_the_compilers_message(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    overrides: dict[str, Any],
    field: str,
    message: str | None,
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(ME_RULES, json=rule_body(**overrides))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    errors = response.json()["errors"]
    assert list(errors) == [field]
    if message is not None:
        assert errors[field] == [message]
    assert (await admin_client.get(ME_RULES)).json() == []  # nothing was saved


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "n" * 201}, "name"),
        ({"name": "a\0b"}, "name"),
        ({"method": "get"}, "method"),
        ({"method": "TRACE"}, "method"),
        ({"matchType": "Glob"}, "matchType"),
        ({"pattern": "/a" + "b" * 2048}, "pattern"),
        ({"pattern": "/a\0"}, "pattern"),
        ({"priority": -1}, "priority"),
        ({"priority": 1.5}, "priority"),
        ({"priority": True}, "priority"),
        ({"priority": "5"}, "priority"),
        ({"priority": 2**31}, "priority"),
        ({"isEnabled": "yes"}, "isEnabled"),
        ({"serviceId": "not-a-uuid"}, "serviceId"),
        ({"developerId": str(uuid.uuid4())}, "developerId"),
        ({"queryConditions": [{"key": "a", "operator": "exists"}] * 21}, "queryConditions"),
        ({"queryConditions": [{"key": "a" * 201, "operator": "exists"}]}, "queryConditions.0.key"),
        (
            {"queryConditions": [{"key": "a", "operator": "like", "value": "x"}]},
            "queryConditions.0.operator",
        ),
        ({"responses": []}, "responses"),
        ({"responses": [response_body()] * 51}, "responses"),
        ({"responses": [response_body(statusCode=99)]}, "responses.0.statusCode"),
        ({"responses": [response_body(), response_body(delayMs=-1)]}, "responses.1.delayMs"),
    ],
)
async def test_invalid_fields_are_422_at_their_path(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    overrides: dict[str, Any],
    field: str,
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(ME_RULES, json=rule_body(**overrides))

    assert response.status_code == 422
    assert field in response.json()["errors"]


async def test_an_unknown_service_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(ME_RULES, json=rule_body(serviceId=str(uuid.uuid4())))

    assert response.status_code == 422
    assert response.json()["errors"] == {"serviceId": ["Unknown Service."]}


async def test_a_rule_can_be_scoped_to_a_service_and_survives_its_deletion(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    admin = await as_developer("root", is_admin=True)
    service = await create_service(admin_client, **{k: v for k, v in SERVICE.items()})
    rule = await create_rule(admin_client, serviceId=service["id"])
    assert rule["serviceId"] == service["id"]

    await admin_client.delete(f"/api/v1/services/{service['id']}")

    as_developer.switch(admin)
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json()["serviceId"] is None


async def test_every_pattern_the_admin_accepts_loads_into_the_gateway_snapshot(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The save check and the Gateway use one compiler, so they can't disagree (§2 risk)."""
    developer = await as_developer("ehtesham")
    patterns = [
        ("Exact", "/a/b/"),
        ("Prefix", "/a/"),
        ("Template", "/a/{id}/{*rest}"),
        ("Regex", r"^/a/(?P<n>\d+)$"),
        ("Regex", "(?i)^/CASE"),
    ]
    for match_type, pattern in patterns:
        await create_rule(
            admin_client,
            matchType=match_type,
            pattern=pattern,
            headerConditions=[{"key": "X-Tenant", "operator": "equals", "value": "a"}],
        )

    async with session_factory() as session:
        snapshot = await load_full(session)

    loaded = snapshot.rules_for(developer.id)
    assert sorted(r.pattern for r in loaded) == sorted(p for _, p in patterns)
    assert all(r.active_response is not None for r in loaded)


# ---- update ----


async def test_updating_a_rule_replaces_its_fields_and_keeps_its_responses(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}",
        json=update_body(
            rule,
            name="Renamed",
            matchType="Template",
            pattern="/limsa/{x}",
            priority=5,
            queryConditions=[{"key": "q", "operator": "equals", "value": "1"}],
        ),
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["name"], updated["matchType"], updated["priority"]) == (
        "Renamed",
        "Template",
        5,
    )
    assert updated["queryConditions"] == [{"key": "q", "operator": "equals", "value": "1"}]
    assert updated["responses"] == rule["responses"]
    assert updated["activeResponseId"] == rule["activeResponseId"]
    assert updated["isEnabled"] is True  # left out of the body: unchanged
    assert updated["updatedAt"] >= rule["updatedAt"]
    entry = (await audit_rows())[-1]
    assert (entry.action, entry.entity_type) == (AuditAction.UPDATE, AuditEntityType.MOCK_RULE)
    assert set(entry.changes) == {"name", "matchType", "pattern", "priority", "queryConditions"}
    assert entry.changes["name"] == {"from": "Dashboard", "to": "Renamed"}


async def test_put_can_set_is_enabled(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}", json=update_body(rule, isEnabled=False)
    )

    assert response.json()["isEnabled"] is False


async def test_putting_the_same_rule_writes_nothing(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    await listener.payloads(2)
    listener.received.clear()

    response = await admin_client.put(f"{ME_RULES}/{rule['id']}", json=update_body(rule))

    assert response.status_code == 200
    assert response.json() == rule
    assert len(await audit_rows()) == 1
    assert await listener.nothing() == []


async def test_a_failed_update_changes_nothing(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}", json=update_body(rule, name="New", pattern="no-slash")
    )

    assert response.status_code == 422
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json() == rule


async def test_update_validates_like_create(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}",
        json=update_body(rule, serviceId=str(uuid.uuid4()), matchType="Regex", pattern="^/(a"),
    )

    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"pattern", "serviceId"}  # both reported at once


# ---- delete ----


async def test_deleting_a_rule_removes_its_responses(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    rule = await create_rule(admin_client, responses=[response_body(), response_body(name="b")])
    await listener.payloads(2)
    listener.received.clear()

    response = await admin_client.delete(f"{ME_RULES}/{rule['id']}")

    assert response.status_code == 204
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).status_code == 404
    async with session_factory() as session:
        assert (await session.scalars(select(MockRule))).all() == []
        assert (await session.scalars(select(MockResponse))).all() == []
    assert (await audit_rows())[-1].action is AuditAction.DELETE
    assert await listener.payloads(1) == [str(developer.id)]


# ---- toggles (PR-08, FR-11) ----


@pytest.mark.req("PR-08")
async def test_toggle_sets_the_state_and_is_idempotent(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    path = f"{ME_RULES}/{rule['id']}/toggle"

    off = await admin_client.post(path, json={"isEnabled": False})
    off_again = await admin_client.post(path, json={"isEnabled": False})
    on = await admin_client.post(path, json={"isEnabled": True})

    assert [r.json()["isEnabled"] for r in (off, off_again, on)] == [False, False, True]
    assert off.json()["responses"] == rule["responses"]
    toggles = [e for e in await audit_rows() if e.action is AuditAction.TOGGLE]
    assert [e.changes["isEnabled"]["to"] for e in toggles] == [False, True]  # the repeat wrote none


@pytest.mark.req("PR-08")
async def test_toggle_needs_a_real_boolean(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    for body in ({}, {"isEnabled": "false"}, {"isEnabled": 0}, {"isEnabled": None}):
        response = await admin_client.post(f"{ME_RULES}/{rule['id']}/toggle", json=body)
        assert response.status_code == 422, body


@pytest.mark.req("PR-08")
async def test_toggle_all_counts_only_the_rules_that_changed(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    await create_rule(admin_client, name="a")
    await create_rule(admin_client, name="b", pattern="/b", isEnabled=False)
    await create_rule(admin_client, name="c", pattern="/c")
    await listener.payloads(3)
    listener.received.clear()

    off = await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})
    off_again = await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})
    on = await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": True})

    assert (off.json(), off_again.json(), on.json()) == (
        {"updated": 2},
        {"updated": 0},
        {"updated": 3},
    )
    assert all(r["isEnabled"] for r in (await admin_client.get(ME_RULES)).json())
    entries = [e for e in await audit_rows() if e.action is AuditAction.TOGGLE]
    assert [e.changes["updated"] for e in entries] == [2, 3]  # the no-op wrote no audit row
    assert entries[0].entity_id == str(developer.id)
    # A bulk UPDATE skips the ORM events, so the endpoint must mark the Developer itself.
    assert await listener.payloads(2) == [str(developer.id)] * 2


@pytest.mark.req("PR-01")
async def test_toggle_all_never_touches_another_developers_rules(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    await create_rule(admin_client)
    await as_developer("bob")
    await create_rule(admin_client)

    await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})

    assert [r["isEnabled"] for r in (await admin_client.get(ME_RULES)).json()] == [False]
    as_developer.switch(alice)
    assert [r["isEnabled"] for r in (await admin_client.get(ME_RULES)).json()] == [True]


async def test_toggle_all_with_no_rules_is_zero(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(f"{ME_RULES}/toggle-all", json={"isEnabled": False})

    assert response.json() == {"updated": 0}
