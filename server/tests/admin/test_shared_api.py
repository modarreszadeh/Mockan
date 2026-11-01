"""Share a MockRule by public link: owner routes and the unauthenticated read (S-1..S-8)."""

import uuid
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog, Developer, MockRule
from tests.admin.builders import ME_RULES, create_rule, response_body, rule_body
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import SERVICE, create_service

pytestmark = [pytest.mark.db]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]
SHARED = "/api/v1/shared/rules"


async def share(client: httpx.AsyncClient, rule: dict[str, object]) -> str:
    response = await client.post(f"{ME_RULES}/{rule['id']}/share")
    assert response.status_code == 200, response.text
    token: str = response.json()["shareToken"]
    return token


async def public_get(app_client: httpx.AsyncClient, token: str) -> httpx.Response:
    """A request without the session cookie, as a teammate who never signed in."""
    app_client.cookies.clear()
    return await app_client.get(f"{SHARED}/{token}")


# ---- owner routes ----


async def test_sharing_returns_a_token_is_idempotent_and_shows_in_the_list(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    assert rule["shareToken"] is None

    first = await admin_client.post(f"{ME_RULES}/{rule['id']}/share")
    again = await admin_client.post(f"{ME_RULES}/{rule['id']}/share")

    assert first.status_code == 200
    assert set(first.json()) == {"shareToken"}
    assert len(first.json()["shareToken"]) == 32
    assert again.json() == first.json()
    listed = (await admin_client.get(ME_RULES)).json()
    assert listed[0]["shareToken"] == first.json()["shareToken"]
    got = (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json()
    assert got["shareToken"] == first.json()["shareToken"]


async def test_sharing_is_not_an_edit(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    await share(admin_client, rule)
    shared = (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json()

    assert shared["updatedAt"] == rule["updatedAt"]
    assert {k: v for k, v in shared.items() if k != "shareToken"} == {
        k: v for k, v in rule.items() if k != "shareToken"
    }


async def test_unsharing_revokes_the_link_is_idempotent_and_a_new_share_has_a_new_token(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    token = await share(admin_client, rule)

    first = await admin_client.delete(f"{ME_RULES}/{rule['id']}/share")
    again = await admin_client.delete(f"{ME_RULES}/{rule['id']}/share")

    assert (first.status_code, again.status_code) == (204, 204)
    assert (await public_get(admin_client, token)).status_code == 404
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json()["shareToken"] is None
    assert await share(admin_client, rule) != token


async def test_another_developer_cannot_share_or_unshare_my_rule(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    rule = await create_rule(admin_client)
    token = await share(admin_client, rule)
    await as_developer("bob")

    shared = await admin_client.post(f"{ME_RULES}/{rule['id']}/share")
    unshared = await admin_client.delete(f"{ME_RULES}/{rule['id']}/share")

    assert (shared.status_code, unshared.status_code) == (404, 404)
    assert shared.json()["code"] == "not_found"
    as_developer.switch(alice)
    assert (await public_get(admin_client, token)).status_code == 200


async def test_a_disabled_developer_cannot_share(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    for method in ("POST", "DELETE"):
        response = await admin_client.request(method, f"{ME_RULES}/{uuid.uuid4()}/share")
        assert response.status_code == 403, method


async def test_sharing_and_unsharing_are_audited_without_the_token(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    developer = await as_developer("ehtesham")
    rule = await create_rule(admin_client)

    token = await share(admin_client, rule)
    await share(admin_client, rule)  # idempotent: no second row
    await admin_client.delete(f"{ME_RULES}/{rule['id']}/share")
    await admin_client.delete(f"{ME_RULES}/{rule['id']}/share")

    rows = [r for r in await audit_rows() if r.action is AuditAction.UPDATE]
    assert [r.changes for r in rows] == [
        {"shared": {"from": False, "to": True}},
        {"shared": {"from": True, "to": False}},
    ]
    assert all(r.entity_type is AuditEntityType.MOCK_RULE for r in rows)
    assert all(r.entity_id == rule["id"] and r.developer_id == developer.id for r in rows)
    assert token not in str([r.changes for r in await audit_rows()])


# ---- the public read ----


async def test_anyone_with_the_link_reads_the_rule_live_without_signing_in(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    owner = await as_developer("root", is_admin=True)
    service = await create_service(admin_client, **SERVICE)
    rule = await create_rule(
        admin_client,
        serviceId=service["id"],
        queryConditions=[{"key": "page", "operator": "equals", "value": "2"}],
        headerConditions=[{"key": "X-Debug", "operator": "exists"}],
        priority=7,
        responses=[
            response_body(name="ok", headers={"X-Team": "core"}),
            response_body(name="boom", statusCode=500, delayMs=300, body='{"e":1}'),
        ],
    )
    token = await share(admin_client, rule)

    response = await public_get(admin_client, token)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex"
    shared = response.json()
    assert set(shared) == {
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
        "service",
        "owner",
        "publicBaseUrl",
        "updatedAt",
    }
    assert (shared["name"], shared["method"], shared["matchType"]) == ("Dashboard", "GET", "Exact")
    assert shared["pattern"] == "/limsa/api/v1/dashboard"
    assert shared["queryConditions"] == [{"key": "page", "operator": "equals", "value": "2"}]
    assert shared["headerConditions"] == [{"key": "X-Debug", "operator": "exists"}]
    assert (shared["priority"], shared["isEnabled"]) == (7, True)
    assert shared["service"] == {"name": "limsa", "pathPrefix": "/limsa"}
    assert shared["owner"] == {"displayName": "Root", "slug": "root"}
    assert shared["publicBaseUrl"] == "https://mock.test"
    assert [r["name"] for r in shared["responses"]] == ["ok", "boom"]
    assert shared["activeResponseId"] == shared["responses"][0]["id"] == rule["activeResponseId"]
    assert shared["responses"][0]["headers"] == {"X-Team": "core"}
    assert shared["responses"][1]["delayMs"] == 300
    text = response.text
    assert str(owner.id) not in text
    assert token not in text
    assert "developerId" not in text
    assert "ssoSubject" not in text
    assert "shareToken" not in text


async def test_the_public_page_follows_later_edits(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    token = await share(admin_client, rule)
    response_id = rule["responses"][0]["id"]

    await admin_client.put(
        f"{ME_RULES}/{rule['id']}/responses/{response_id}", json=response_body(statusCode=418)
    )
    await admin_client.post(f"{ME_RULES}/{rule['id']}/toggle", json={"isEnabled": False})

    shared = (await public_get(admin_client, token)).json()
    assert shared["responses"][0]["statusCode"] == 418
    assert shared["isEnabled"] is False
    assert shared["service"] is None


async def test_an_unknown_token_is_a_404_problem_with_the_same_headers(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await public_get(admin_client, "nope")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["cache-control"] == "no-store"


async def test_a_disabled_owners_link_is_a_404(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = await as_developer("ehtesham")
    token = await share(admin_client, await create_rule(admin_client))
    async with session_factory() as session:
        found = await session.get(Developer, owner.id)
        assert found is not None
        found.is_enabled = False
        await session.commit()

    assert (await public_get(admin_client, token)).status_code == 404


async def test_deleting_the_rule_kills_the_link(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client)
    token = await share(admin_client, rule)

    await admin_client.delete(f"{ME_RULES}/{rule['id']}")

    assert (await public_get(admin_client, token)).status_code == 404


# ---- what sharing must not leak into ----


async def test_the_share_token_is_not_exported_and_import_never_sets_it(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await as_developer("ehtesham")
    token = await share(admin_client, await create_rule(admin_client))

    exported = await admin_client.get(f"{ME_RULES}/export")
    assert "shareToken" not in exported.text
    assert token not in exported.text
    imported = await admin_client.post(f"{ME_RULES}/import?mode=replace", json=exported.json())
    assert imported.status_code == 200, imported.text

    async with session_factory() as session:
        tokens = list(await session.scalars(select(MockRule.share_token)))
    assert tokens == [None]
    assert (await public_get(admin_client, token)).status_code == 404


async def test_the_share_token_cannot_be_set_through_the_rule_inputs(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    created = await admin_client.post(ME_RULES, json=rule_body(shareToken="mine"))
    rule = await create_rule(admin_client)
    updated = await admin_client.put(
        f"{ME_RULES}/{rule['id']}", json={**rule_body(), "shareToken": "mine"}
    )

    assert (created.status_code, updated.status_code) == (422, 422)
