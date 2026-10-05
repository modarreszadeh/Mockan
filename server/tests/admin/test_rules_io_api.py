"""`/me/rules/export` and `/me/rules/import` (FR-12, PR-14): validated, all or nothing."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import AuditAction
from mockan.infrastructure.db.models import AuditLog, MockResponse, MockRule
from tests.admin.builders import ME_RULES, create_rule, response_body
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import create_service
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-14")]

EXPORT = f"{ME_RULES}/export"
IMPORT = f"{ME_RULES}/import"
AuditRows = Callable[[], Awaitable[list[AuditLog]]]


def exported_rule(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "Dashboard",
        "method": "GET",
        "matchType": "Exact",
        "pattern": "/limsa/dash",
        "queryConditions": [],
        "headerConditions": [],
        "priority": 100,
        "isEnabled": True,
        "serviceName": None,
        "activeResponse": 0,
        "responses": [response_body()],
        **overrides,
    }


async def export(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(EXPORT)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# ---- export ----


async def test_an_empty_workspace_exports_an_empty_list(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    assert await export(admin_client) == {"version": 1, "rules": []}


async def test_the_export_has_no_ids_and_keeps_everything_else(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    await create_service(admin_client, name="limsa", pathPrefix="/limsa")
    service = (await admin_client.get("/api/v1/services")).json()[0]
    await as_developer("ehtesham")
    created = await create_rule(
        admin_client,
        serviceId=service["id"],
        priority=3,
        queryConditions=[{"key": "page", "operator": "equals", "value": "2"}],
        headerConditions=[{"key": "debug", "operator": "exists"}],
        responses=[
            response_body(name="ok"),
            response_body(name="boom", statusCode=500, body="x", delayMs=10),
        ],
    )
    second = created["responses"][1]["id"]
    await admin_client.post(f"{ME_RULES}/{created['id']}/responses/{second}/activate")
    await admin_client.post(f"{ME_RULES}/{created['id']}/toggle", json={"isEnabled": False})

    file = await export(admin_client)

    assert file["version"] == 1
    (rule,) = file["rules"]
    assert rule == {
        "name": "Dashboard",
        "method": "GET",
        "matchType": "Exact",
        "pattern": "/limsa/api/v1/dashboard",
        "queryConditions": [{"key": "page", "operator": "equals", "value": "2"}],
        "headerConditions": [{"key": "debug", "operator": "exists"}],
        "priority": 3,
        "isEnabled": False,
        "serviceName": "limsa",
        "activeResponse": 1,  # the second response is the active one
        "responses": [
            {
                "name": "ok",
                "statusCode": 200,
                "headers": {"X-A": "1"},
                "contentType": "application/json",
                "body": '{"ok":true}',
                "bodyMode": "Static",
                "delayMs": 0,
            },
            {
                "name": "boom",
                "statusCode": 500,
                "headers": {"X-A": "1"},
                "contentType": "application/json",
                "body": "x",
                "bodyMode": "Static",
                "delayMs": 10,
            },
        ],
    }
    text = json.dumps(file)
    assert (
        created["id"] not in text
        and created["developerId"] not in text
        and service["id"] not in text
    )


@pytest.mark.req("PR-01")
async def test_the_export_only_has_my_rules(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("alice")
    await create_rule(admin_client, name="alices")
    await as_developer("bob")
    await create_rule(admin_client, name="bobs", pattern="/b")

    assert [r["name"] for r in (await export(admin_client))["rules"]] == ["bobs"]


async def test_export_is_not_taken_for_a_rule_id(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    assert (await admin_client.get(EXPORT)).status_code == 200  # not a 404 for a malformed id
    assert (await admin_client.get(f"{ME_RULES}/not-a-uuid")).status_code == 404


# ---- round trip ----


async def test_a_workspace_exported_then_imported_elsewhere_is_the_same_set(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    await create_service(admin_client, name="limsa", pathPrefix="/limsa")
    service = (await admin_client.get("/api/v1/services")).json()[0]
    await as_developer("alice")
    await create_rule(admin_client, serviceId=service["id"], name="a", priority=1)
    await create_rule(
        admin_client,
        name="b",
        pattern="/orders/{id}",
        matchType="Template",
        responses=[
            response_body(name="t", bodyMode="Template", body="{{ route.id }}"),
            response_body(name="other", statusCode=404),
        ],
    )
    file = await export(admin_client)
    await as_developer("bob")

    imported = await admin_client.post(IMPORT, json=file)

    assert imported.status_code == 200
    assert imported.json() == {"mode": "merge", "created": 2, "deleted": 0}
    assert await export(admin_client) == file  # the same set, in the same order, ids aside
    rules = (await admin_client.get(ME_RULES)).json()
    assert all(
        r["activeResponseId"] == r["responses"][file["rules"][i]["activeResponse"]]["id"]
        for i, r in enumerate(rules)
    )
    assert rules[0]["serviceId"] == service["id"]  # the Service name was resolved again


# ---- import: modes ----


async def test_merge_adds_to_existing_rules_and_replace_swaps_them(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    await create_rule(admin_client, name="mine", pattern="/mine")
    await listener.payloads(2)
    listener.received.clear()

    merged = await admin_client.post(
        IMPORT, json={"version": 1, "rules": [exported_rule(name="new")]}
    )
    assert merged.json() == {"mode": "merge", "created": 1, "deleted": 0}
    assert [r["name"] for r in (await admin_client.get(ME_RULES)).json()] == ["mine", "new"]

    replaced = await admin_client.post(
        f"{IMPORT}?mode=replace",
        json={
            "version": 1,
            "rules": [exported_rule(name="a", pattern="/a"), exported_rule(name="b", pattern="/b")],
        },
    )
    assert replaced.json() == {"mode": "replace", "created": 2, "deleted": 2}
    assert [r["name"] for r in (await admin_client.get(ME_RULES)).json()] == ["a", "b"]

    entry = (await audit_rows())[-1]
    assert entry.action is AuditAction.CREATE
    assert entry.changes == {"import": "replace", "created": 2, "deleted": 2, "rules": ["a", "b"]}
    assert set(await listener.payloads(1)) == {str(developer.id)}


async def test_replace_with_an_empty_file_clears_the_workspace(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await as_developer("ehtesham")
    await create_rule(admin_client)

    result = await admin_client.post(f"{IMPORT}?mode=replace", json={"version": 1, "rules": []})

    assert result.json() == {"mode": "replace", "created": 0, "deleted": 1}
    async with session_factory() as session:
        assert (await session.scalars(select(MockRule))).all() == []
        assert (await session.scalars(select(MockResponse))).all() == []  # CASCADE


async def test_replace_never_touches_another_developers_rules(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    await create_rule(admin_client, name="alices")
    await as_developer("bob")

    await admin_client.post(f"{IMPORT}?mode=replace", json={"version": 1, "rules": []})

    as_developer.switch(alice)
    assert [r["name"] for r in (await admin_client.get(ME_RULES)).json()] == ["alices"]


async def test_importing_twice_with_merge_duplicates_as_documented(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    file = {"version": 1, "rules": [exported_rule()]}

    await admin_client.post(IMPORT, json=file)
    await admin_client.post(IMPORT, json=file)

    assert len((await admin_client.get(ME_RULES)).json()) == 2


# ---- import: validation, all or nothing ----


async def test_every_problem_is_reported_at_once_and_nothing_is_saved(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    await create_rule(admin_client, name="keep")
    file = {
        "version": 1,
        "rules": [
            exported_rule(name="fine", pattern="/ok"),
            exported_rule(name="bad pattern", matchType="Regex", pattern=r"^/(a)\1"),
            exported_rule(
                name="bad bits",
                serviceName="nope",
                activeResponse=3,
                responses=[
                    response_body(),
                    response_body(bodyMode="Template", body="{% for %}"),
                ],
            ),
            exported_rule(
                name="bad conditions", queryConditions=[{"key": "", "operator": "exists"}]
            ),
        ],
    }

    response = await admin_client.post(f"{IMPORT}?mode=replace", json=file)

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert errors["rules.1.pattern"] == ["RE2 doesn't support backreferences."]
    assert errors["rules.2.serviceName"] == ["Unknown Service “nope”."]
    assert errors["rules.2.activeResponse"] == [
        "Use a number from 0 to 1: the index of a response."
    ]
    assert errors["rules.2.responses.1.body"][0].startswith("Line 1:")
    assert errors["rules.3.queryConditions.0.key"] == ["Enter a name."]
    assert not any(key.startswith("rules.0.") for key in errors)
    assert [r["name"] for r in (await admin_client.get(ME_RULES)).json()] == [
        "keep"
    ]  # replace didn't run


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"rules": []}, "version"),
        ({"version": 2, "rules": []}, "version"),
        ({"version": 1}, "rules"),
        ({"version": 1, "rules": [exported_rule(responses=[])]}, "rules.0.responses"),
        ({"version": 1, "rules": [exported_rule(method="get")]}, "rules.0.method"),
        ({"version": 1, "rules": [exported_rule(name="")]}, "rules.0.name"),
        ({"version": 1, "rules": [exported_rule(activeResponse=-1)]}, "rules.0.activeResponse"),
        ({"version": 1, "rules": [exported_rule(id="x")]}, "rules.0.id"),
        (
            {"version": 1, "rules": [exported_rule(responses=[response_body(statusCode=99)])]},
            "rules.0.responses.0.statusCode",
        ),
        (
            {
                "version": 1,
                "rules": [exported_rule(responses=[response_body(bodyMode="ProxyAndPatch")])],
            },
            "rules.0.responses.0.bodyMode",
        ),
        ({"version": 1, "rules": [exported_rule()] * 201}, "rules"),
        ({"version": 1, "rules": [], "extra": 1}, "extra"),
    ],
)
async def test_malformed_files_are_422_at_their_path(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, body: dict[str, Any], field: str
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(IMPORT, json=body)

    assert response.status_code == 422
    assert field in response.json()["errors"]


async def test_an_unknown_mode_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(f"{IMPORT}?mode=overwrite", json={"version": 1, "rules": []})

    assert response.status_code == 422


async def test_a_file_that_is_not_json_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(
        IMPORT, content=b"not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert "isn't valid JSON" in response.json()["detail"]


async def test_imported_rules_are_enabled_unless_the_file_says_otherwise(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    file = {
        "version": 1,
        "rules": [
            {
                "name": "defaults",
                "matchType": "Prefix",
                "pattern": "/a",
                "responses": [{"name": "r", "statusCode": 200}],
            },
            exported_rule(name="off", pattern="/b", isEnabled=False),
        ],
    }

    await admin_client.post(IMPORT, json=file)

    rules = (await admin_client.get(ME_RULES)).json()
    assert [(r["name"], r["isEnabled"], r["method"], r["priority"]) for r in rules] == [
        ("defaults", True, "ANY", 100),
        ("off", False, "GET", 100),
    ]


async def test_a_disabled_developer_can_export_but_not_import(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    assert (await admin_client.get(EXPORT)).status_code == 200
    blocked = await admin_client.post(IMPORT, json={"version": 1, "rules": []})
    assert (blocked.status_code, blocked.json()["code"]) == (403, "developer_disabled")


async def test_both_need_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get(EXPORT)).status_code == 401
    assert (await admin_client.post(IMPORT, json={"version": 1, "rules": []})).status_code == 401
