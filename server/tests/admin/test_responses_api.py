"""`/me/rules/{id}/responses`: scenarios, the active one, the last-response rule (PR-06, G-3)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog, MockResponse
from tests.admin.builders import ME_RULES, create_rule, response_body
from tests.admin.conftest import AsDeveloper
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-06")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]


async def get_rule(client: httpx.AsyncClient, rule_id: str) -> dict[str, Any]:
    body: dict[str, Any] = (await client.get(f"{ME_RULES}/{rule_id}")).json()
    return body


# ---- create ----


async def test_adding_a_response_does_not_change_the_active_one(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses", json=response_body(name="boom", statusCode=500)
    )

    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["statusCode"], created["ruleId"]) == ("boom", 500, rule["id"])
    after = await get_rule(admin_client, rule["id"])
    assert [r["id"] for r in after["responses"]] == [rule["responses"][0]["id"], created["id"]]
    assert after["activeResponseId"] == rule["activeResponseId"]
    assert after["updatedAt"] >= rule["updatedAt"]


async def test_a_response_gets_its_defaults(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses", json={"name": "bare", "statusCode": 204}
    )

    created = response.json()
    assert (created["contentType"], created["body"], created["delayMs"], created["headers"]) == (
        "application/json",
        "",
        0,
        {},
    )
    assert created["bodyMode"] == "Static"


async def test_a_body_that_is_not_json_is_accepted(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    """PR-06: JSON checking is the Panel's job, so a deliberately broken body stays possible."""
    await as_developer("ehtesham")

    rule = await create_rule(
        admin_client, responses=[response_body(body="{ not json", contentType="application/json")]
    )

    assert rule["responses"][0]["body"] == "{ not json"


async def test_creating_a_response_audits_without_its_body(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    await listener.payloads(2)
    listener.received.clear()

    created = (
        await admin_client.post(
            f"{ME_RULES}/{rule['id']}/responses",
            json=response_body(
                name="secret", headers={"Set-Cookie": "sid=abc", "X-Api-Key": "k"}, body="hunter2"
            ),
        )
    ).json()

    entry = (await audit_rows())[-1]
    assert (entry.action, entry.entity_type) == (AuditAction.CREATE, AuditEntityType.MOCK_RESPONSE)
    assert entry.entity_id == created["id"]
    assert entry.changes["ruleId"] == rule["id"]
    assert entry.changes["headers"] == {"Set-Cookie": "***", "X-Api-Key": "***"}
    assert (entry.changes["bodyBytes"], len(entry.changes["bodySha256"])) == (7, 16)
    assert "hunter2" not in str(entry.changes)
    assert "sid=abc" not in str(entry.changes)
    assert set(await listener.payloads(1)) == {str(developer.id)}  # a response names its owner


async def test_at_most_fifty_responses_per_rule(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(
        admin_client, responses=[response_body(name=f"r{i}") for i in range(50)]
    )

    response = await admin_client.post(f"{ME_RULES}/{rule['id']}/responses", json=response_body())

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert "at most 50" in response.json()["detail"]


# ---- validation ----

ONE_MIB = 1_048_576


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "n" * 101}, "name"),
        ({"statusCode": 99}, "statusCode"),
        ({"statusCode": 600}, "statusCode"),
        ({"statusCode": "200"}, "statusCode"),
        ({"statusCode": True}, "statusCode"),
        ({"statusCode": 200.5}, "statusCode"),
        ({"delayMs": -1}, "delayMs"),
        ({"delayMs": 30_001}, "delayMs"),
        ({"delayMs": 1.5}, "delayMs"),
        ({"body": "a" * (ONE_MIB + 1)}, "body"),
        ({"body": "é" * (ONE_MIB // 2 + 1)}, "body"),  # bytes, not characters
        ({"body": "x\0y"}, "body"),
        ({"contentType": "a" * 256}, "contentType"),
        ({"contentType": "text/\0plain"}, "contentType"),
        ({"headers": {"Bad Name": "x"}}, "headers"),
        ({"headers": {"X-A": "a\r\nSet-Cookie: x=y"}}, "headers"),
        ({"headers": {"X-A": "a\0"}}, "headers"),
        ({"headers": {f"X-{i}": "v" for i in range(51)}}, "headers"),
        ({"headers": {"X-A": 1}}, "headers.X-A"),
        ({"bodyMode": "Template"}, "bodyMode"),
        ({"bodyMode": "ProxyAndPatch"}, "bodyMode"),
        ({"bodyMode": "Markdown"}, "bodyMode"),
        ({"ruleId": str(uuid.uuid4())}, "ruleId"),
        ({"id": str(uuid.uuid4())}, "id"),
    ],
)
async def test_invalid_response_fields_are_422(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    overrides: dict[str, Any],
    field: str,
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    create = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses", json=response_body(**overrides)
    )
    update = await admin_client.put(
        f"{ME_RULES}/{rule['id']}/responses/{rule['activeResponseId']}",
        json=response_body(**overrides),
    )

    for response in (create, update):
        assert response.status_code == 422
        assert field in response.json()["errors"]
    assert await get_rule(admin_client, rule["id"]) == rule


async def test_a_lone_surrogate_in_the_body_is_422_not_a_500(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    """JSON can spell `\\ud800`; it isn't UTF-8 text, so it can't be stored or served."""
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses",
        content=b'{"name":"s","statusCode":200,"body":"\\ud800"}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == {"body": ["Body must be valid UTF-8 text."]}


@pytest.mark.parametrize(
    "name", ["Content-Type", "content-length", "Transfer-Encoding", "Connection", "Upgrade", "TE"]
)
async def test_headers_that_belong_to_the_server_are_rejected(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, name: str
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses", json=response_body(headers={name: "x"})
    )

    assert response.status_code == 422
    assert "can't be overridden" in response.json()["errors"]["headers"][0]


async def test_the_limits_themselves_are_allowed(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    rule = await create_rule(
        admin_client,
        responses=[
            response_body(name="n" * 100, statusCode=100, delayMs=30_000, body="a" * ONE_MIB),
            response_body(statusCode=599, delayMs=0, body="é" * (ONE_MIB // 2)),
        ],
    )

    assert [r["statusCode"] for r in rule["responses"]] == [100, 599]


async def test_errors_name_the_response_that_failed_when_creating_a_rule(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(
        ME_RULES,
        json={
            "name": "r",
            "matchType": "Exact",
            "pattern": "/a",
            "responses": [
                {"name": "ok", "statusCode": 200},
                {"name": "", "statusCode": 700, "bodyMode": "Template"},
            ],
        },
    )

    assert response.status_code == 422
    assert set(response.json()["errors"]) == {
        "responses.1.name",
        "responses.1.statusCode",
        "responses.1.bodyMode",
    }


# ---- update ----


async def test_updating_a_response(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    active = rule["activeResponseId"]

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}/responses/{active}",
        json=response_body(name="renamed", statusCode=404, body="gone", delayMs=250),
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["id"], updated["name"], updated["statusCode"]) == (active, "renamed", 404)
    assert (updated["body"], updated["delayMs"]) == ("gone", 250)
    assert updated["createdAt"] == rule["responses"][0]["createdAt"]
    after = await get_rule(admin_client, rule["id"])
    assert after["responses"] == [updated]
    assert after["updatedAt"] >= rule["updatedAt"]
    entry = (await audit_rows())[-1]
    assert (entry.action, entry.entity_type) == (AuditAction.UPDATE, AuditEntityType.MOCK_RESPONSE)
    assert {"name", "statusCode", "delayMs", "bodyBytes", "bodySha256"} <= set(entry.changes)
    assert "body" not in entry.changes


async def test_putting_the_same_response_writes_nothing(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    await listener.payloads(2)
    listener.received.clear()

    response = await admin_client.put(
        f"{ME_RULES}/{rule['id']}/responses/{rule['activeResponseId']}", json=response_body()
    )

    assert response.status_code == 200
    assert response.json() == rule["responses"][0]
    assert len(await audit_rows()) == 1
    assert await listener.nothing() == []


# ---- delete, activate ----


async def test_deleting_a_response_that_is_not_active(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(
        admin_client, responses=[response_body(name="a"), response_body(name="b")]
    )
    second = rule["responses"][1]["id"]

    response = await admin_client.delete(f"{ME_RULES}/{rule['id']}/responses/{second}")

    assert response.status_code == 204
    after = await get_rule(admin_client, rule["id"])
    assert [r["name"] for r in after["responses"]] == ["a"]
    assert after["activeResponseId"] == rule["activeResponseId"]
    assert (await audit_rows())[-1].action is AuditAction.DELETE


async def test_deleting_the_active_response_activates_another(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(
        admin_client, responses=[response_body(name="a"), response_body(name="b")]
    )

    response = await admin_client.delete(
        f"{ME_RULES}/{rule['id']}/responses/{rule['activeResponseId']}"
    )

    assert response.status_code == 204
    after = await get_rule(admin_client, rule["id"])
    assert [r["name"] for r in after["responses"]] == ["b"]
    assert after["activeResponseId"] == after["responses"][0]["id"]


async def test_the_last_response_can_not_be_deleted(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """G-3: a rule always has an active response."""
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.delete(
        f"{ME_RULES}/{rule['id']}/responses/{rule['activeResponseId']}"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "last_response"
    assert await get_rule(admin_client, rule["id"]) == rule
    async with session_factory() as session:
        assert len((await session.scalars(select(MockResponse))).all()) == 1


async def test_activating_a_response_returns_the_rule(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(
        admin_client, responses=[response_body(name="a"), response_body(name="b")]
    )
    second = rule["responses"][1]["id"]

    response = await admin_client.post(f"{ME_RULES}/{rule['id']}/responses/{second}/activate")

    assert response.status_code == 200
    assert response.json()["activeResponseId"] == second
    assert response.json()["id"] == rule["id"]
    assert (await get_rule(admin_client, rule["id"]))["activeResponseId"] == second
    entry = (await audit_rows())[-1]
    assert (entry.action, entry.entity_type) == (
        AuditAction.ACTIVATE,
        AuditEntityType.MOCK_RESPONSE,
    )
    assert entry.changes["activeResponseId"] == {"from": rule["activeResponseId"], "to": second}


async def test_activating_the_active_response_writes_nothing(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    response = await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses/{rule['activeResponseId']}/activate"
    )

    assert response.status_code == 200
    assert response.json() == rule
    assert len(await audit_rows()) == 1


async def test_a_response_of_another_rule_is_a_404(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    first = await create_rule(admin_client, name="first")
    second = await create_rule(admin_client, name="second", pattern="/b")
    foreign = second["activeResponseId"]
    base = f"{ME_RULES}/{first['id']}/responses/{foreign}"

    for method, path, body in [
        ("PUT", base, response_body()),
        ("DELETE", base, None),
        ("POST", f"{base}/activate", None),
    ]:
        response = await admin_client.request(method, path, json=body)
        assert response.status_code == 404, method
        assert response.json()["code"] == "not_found"
    assert await get_rule(admin_client, second["id"]) == second


async def test_activating_changes_the_rule_notification(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, listener: Listener
) -> None:
    developer = await as_developer("ehtesham")
    rule = await create_rule(
        admin_client, responses=[response_body(name="a"), response_body(name="b")]
    )
    await listener.payloads(2)
    listener.received.clear()

    await admin_client.post(
        f"{ME_RULES}/{rule['id']}/responses/{rule['responses'][1]['id']}/activate"
    )

    assert await listener.payloads(1) == [str(developer.id)]
