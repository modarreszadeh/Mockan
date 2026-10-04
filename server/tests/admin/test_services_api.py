"""Service catalog (PR-10, PR-15, D-08): reads for everyone, writes for admins, audited."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import (
    AuditLog,
    DeveloperServiceSetting,
    MockRule,
    ServiceEnvironment,
)
from tests.admin.conftest import AsDeveloper
from tests.infrastructure.helpers import make_rule
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-10")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]

SERVICE = {
    "name": "limsa",
    "pathPrefix": "/limsa",
    "stripPrefix": False,
    "rewriteOrigin": False,
    "defaultEnvironment": "stage",
}


def environment(
    name: str = "stage", host: str = "limsa.dev.internal", **extra: Any
) -> dict[str, Any]:
    return {
        "environment": name,
        "baseUrl": f"https://{host}",
        "timeoutSeconds": 100,
        "extraHeaders": {},
        **extra,
    }


async def create_service(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/services", json={**SERVICE, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def create_environment(
    client: httpx.AsyncClient, service_id: str, **kwargs: Any
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/services/{service_id}/environments", json=environment(**kwargs)
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# ---- reading ----


async def test_everyone_can_list_the_catalog_with_environments(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    await create_environment(admin_client, service["id"], name="stage")
    await create_environment(admin_client, service["id"], name="dev")
    await create_service(admin_client, name="alpha", pathPrefix="/alpha")

    await as_developer("ehtesham")
    response = await admin_client.get("/api/v1/services")

    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["alpha", "limsa"]
    limsa = response.json()[1]
    assert set(limsa) == {
        "id",
        "name",
        "pathPrefix",
        "stripPrefix",
        "rewriteOrigin",
        "defaultEnvironment",
        "environments",
        "createdAt",
        "updatedAt",
    }
    assert [e["environment"] for e in limsa["environments"]] == ["dev", "stage"]
    assert set(limsa["environments"][0]) == {
        "id",
        "serviceId",
        "environment",
        "baseUrl",
        "timeoutSeconds",
        "extraHeaders",
        "createdAt",
        "updatedAt",
    }


async def test_the_catalog_needs_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/v1/services")).status_code == 401


# ---- authorisation ----


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/services"),
        ("PUT", "/api/v1/services/{sid}"),
        ("DELETE", "/api/v1/services/{sid}"),
        ("POST", "/api/v1/services/{sid}/environments"),
        ("PUT", "/api/v1/services/{sid}/environments/{eid}"),
        ("DELETE", "/api/v1/services/{sid}/environments/{eid}"),
    ],
)
async def test_non_admins_cannot_write_the_catalog(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, method: str, path: str
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    env = await create_environment(admin_client, service["id"])
    await as_developer("ehtesham")

    response = await admin_client.request(
        method,
        path.format(sid=service["id"], eid=env["id"]),
        json=environment() if "environments" in path else SERVICE,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert len((await admin_client.get("/api/v1/services")).json()) == 1  # nothing changed


async def test_a_disabled_admin_cannot_write(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True, is_enabled=False)

    response = await admin_client.post("/api/v1/services", json=SERVICE)

    assert response.status_code == 403
    assert response.json()["code"] == "developer_disabled"


# ---- creating and updating Services ----


async def test_creating_a_service_audits_and_notifies_the_catalog(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    admin = await as_developer("root", is_admin=True)
    await listener.payloads(1)  # the fixture row

    response = await admin_client.post("/api/v1/services", json=SERVICE)

    assert response.status_code == 201
    body = response.json()
    assert body["environments"] == []
    assert body["name"] == "limsa"
    (entry,) = await audit_rows()
    assert (entry.action, entry.entity_type) == (AuditAction.CREATE, AuditEntityType.SERVICE)
    assert entry.entity_id == body["id"]
    assert entry.developer_id == admin.id
    assert entry.changes["pathPrefix"] == "/limsa"
    assert await listener.payloads(1) == ["catalog"]


async def test_service_defaults_match_the_database(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)

    response = await admin_client.post(
        "/api/v1/services", json={"name": "limsa", "pathPrefix": "/limsa"}
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["stripPrefix"], body["rewriteOrigin"], body["defaultEnvironment"]) == (
        False,
        False,
        "stage",
    )


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "Limsa"}, "name"),
        ({"name": "1limsa"}, "name"),
        ({"name": "n" * 101}, "name"),
        ({"pathPrefix": "limsa"}, "pathPrefix"),
        ({"pathPrefix": "/limsa/"}, "pathPrefix"),
        ({"pathPrefix": "/"}, "pathPrefix"),
        ({"pathPrefix": "//limsa"}, "pathPrefix"),
        ({"pathPrefix": "/li msa"}, "pathPrefix"),
        ({"pathPrefix": "/" + "p" * 200}, "pathPrefix"),
        ({"defaultEnvironment": "prod"}, "defaultEnvironment"),
        ({"stripPrefix": "yes"}, "stripPrefix"),
        ({"rewriteOrigin": 1}, "rewriteOrigin"),
    ],
)
async def test_invalid_service_fields_are_422(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    overrides: dict[str, Any],
    field: str,
) -> None:
    await as_developer("root", is_admin=True)

    response = await admin_client.post("/api/v1/services", json={**SERVICE, **overrides})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert list(response.json()["errors"]) == [field]


async def test_a_nested_path_prefix_is_allowed(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)

    service = await create_service(admin_client, pathPrefix="/api/limsa-v2")

    assert service["pathPrefix"] == "/api/limsa-v2"


async def test_duplicate_names_and_prefixes_are_409(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    await create_service(admin_client)

    same_name = await admin_client.post("/api/v1/services", json={**SERVICE, "pathPrefix": "/x"})
    same_prefix = await admin_client.post("/api/v1/services", json={**SERVICE, "name": "other"})
    same_prefix_other_case = await admin_client.post(
        "/api/v1/services", json={**SERVICE, "name": "other", "pathPrefix": "/LIMSA"}
    )

    assert same_name.status_code == 409
    assert same_name.json()["code"] == "name_taken"
    assert list(same_name.json()["errors"]) == ["name"]
    for response in (same_prefix, same_prefix_other_case):
        assert response.status_code == 409
        assert response.json()["code"] == "path_prefix_taken"
        assert list(response.json()["errors"]) == ["pathPrefix"]


async def test_updating_a_service(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.put(
        f"/api/v1/services/{service['id']}",
        json={**SERVICE, "stripPrefix": True, "defaultEnvironment": "dev"},
    )

    assert response.status_code == 200
    assert response.json()["stripPrefix"] is True
    assert response.json()["defaultEnvironment"] == "dev"
    assert response.json()["updatedAt"] >= service["updatedAt"]
    update = (await audit_rows())[-1]
    assert update.action is AuditAction.UPDATE
    assert update.changes == {
        "stripPrefix": {"from": False, "to": True},
        "defaultEnvironment": {"from": "stage", "to": "dev"},
    }


async def test_updating_a_service_to_its_own_values_is_a_no_op(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    await listener.payloads(2)

    response = await admin_client.put(f"/api/v1/services/{service['id']}", json=SERVICE)

    assert response.status_code == 200
    assert len(await audit_rows()) == 1  # only the create
    assert await listener.nothing() == []


async def test_a_service_can_not_take_another_ones_name_or_prefix(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    await create_service(admin_client)
    other = await create_service(admin_client, name="other", pathPrefix="/other")

    taken_name = await admin_client.put(
        f"/api/v1/services/{other['id']}", json={**SERVICE, "pathPrefix": "/other"}
    )
    taken_prefix = await admin_client.put(
        f"/api/v1/services/{other['id']}", json={**SERVICE, "name": "other"}
    )

    assert taken_name.json()["code"] == "name_taken"
    assert taken_prefix.json()["code"] == "path_prefix_taken"


async def test_unknown_services_are_404(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    missing = uuid.uuid4()

    for method, path in (
        ("PUT", f"/api/v1/services/{missing}"),
        ("DELETE", f"/api/v1/services/{missing}"),
        ("POST", f"/api/v1/services/{missing}/environments"),
    ):
        response = await admin_client.request(
            method, path, json=environment() if path.endswith("environments") else SERVICE
        )
        assert response.status_code == 404, (method, path)
        assert response.json()["code"] == "not_found"


async def test_deleting_a_service_cascades_and_unscopes_rules(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    admin = await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    env = await create_environment(admin_client, service["id"])
    async with session_factory() as session:
        rule, response = make_rule(admin, service_id=uuid.UUID(service["id"]))
        session.add(rule)
        await session.flush()
        response.rule_id = rule.id
        session.add(response)
        session.add(
            DeveloperServiceSetting(
                developer_id=admin.id,
                service_id=uuid.UUID(service["id"]),
                service_environment_id=uuid.UUID(env["id"]),
            )
        )
        await session.commit()
    await listener.payloads(1)
    listener.received.clear()

    response = await admin_client.delete(f"/api/v1/services/{service['id']}")

    assert response.status_code == 204
    assert (await admin_client.get("/api/v1/services")).json() == []
    async with session_factory() as session:
        assert (await session.scalars(select(ServiceEnvironment))).all() == []
        assert (await session.scalars(select(DeveloperServiceSetting))).all() == []
        (kept,) = (await session.scalars(select(MockRule))).all()
        assert kept.service_id is None
    assert (await audit_rows())[-1].action is AuditAction.DELETE
    assert "catalog" in await listener.payloads(1)


# ---- ServiceEnvironments ----


async def test_creating_an_environment(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments",
        json=environment(
            "dev", host="limsa.dev.internal", timeoutSeconds=30, extraHeaders={"X-Env": "dev"}
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["serviceId"] == service["id"]
    assert (body["environment"], body["timeoutSeconds"]) == ("dev", 30)
    assert body["baseUrl"] == "https://limsa.dev.internal"
    assert body["extraHeaders"] == {"X-Env": "dev"}
    listed = (await admin_client.get("/api/v1/services")).json()[0]["environments"]
    assert [e["id"] for e in listed] == [body["id"]]
    entry = (await audit_rows())[-1]
    assert (entry.action, entry.entity_type) == (
        AuditAction.CREATE,
        AuditEntityType.SERVICE_ENVIRONMENT,
    )
    assert entry.entity_id == body["id"]


async def test_environment_timeout_defaults_to_100_seconds(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments",
        json={"environment": "dev", "baseUrl": "https://limsa.dev.internal"},
    )

    assert response.json()["timeoutSeconds"] == 100
    assert response.json()["extraHeaders"] == {}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://evil.example.com",
        "https://dev.internal",  # `*.dev.internal` never matches the apex (NFR-06)
        "https://limsa.dev.internal.evil.com",
        "https://prod.internal",
    ],
)
async def test_hosts_outside_the_allowlist_are_rejected(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, base_url: str
) -> None:
    """PR-15: saving a non-allowlisted base URL → 422."""
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments",
        json={**environment(), "baseUrl": base_url},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "upstream_host_not_allowed"
    assert list(body["errors"]) == ["baseUrl"]


@pytest.mark.parametrize(
    "base_url",
    [
        "https://identity.stage.internal",
        "HTTPS://IDENTITY.STAGE.INTERNAL:8443/identity",
        "http://a.b.dev.internal",
    ],
)
async def test_allowlisted_hosts_are_accepted(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, base_url: str
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments",
        json={**environment(), "baseUrl": base_url},
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "base_url",
    [
        "limsa.dev.internal",
        "ftp://limsa.dev.internal",
        "https://",
        "https://limsa.dev.internal:notaport",
        "https://user:pw@limsa.dev.internal",
        "https://identity.stage.internal@evil.com",
        "https://limsa.dev.internal/?a=1",
        "https://limsa.dev.internal/#frag",
        "",
    ],
)
async def test_malformed_base_urls_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, base_url: str
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments",
        json={**environment(), "baseUrl": base_url},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert list(response.json()["errors"]) == ["baseUrl"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"timeoutSeconds": 0}, "timeoutSeconds"),
        ({"timeoutSeconds": 3601}, "timeoutSeconds"),
        ({"timeoutSeconds": True}, "timeoutSeconds"),
        ({"timeoutSeconds": 1.5}, "timeoutSeconds"),
        ({"environment": "prod"}, "environment"),
        ({"extraHeaders": {"Bad Name": "x"}}, "extraHeaders"),
        ({"extraHeaders": {"X-A": "line\r\nbreak: 1"}}, "extraHeaders"),
        ({"extraHeaders": {f"X-{i}": "v" for i in range(51)}}, "extraHeaders"),
        ({"extraHeaders": {"X-A": 1}}, "extraHeaders.X-A"),
    ],
)
async def test_invalid_environment_fields_are_422(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    overrides: dict[str, Any],
    field: str,
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments", json={**environment(), **overrides}
    )

    assert response.status_code == 422
    assert list(response.json()["errors"]) == [field]


async def test_a_duplicate_environment_is_409(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    await create_environment(admin_client, service["id"], name="dev")

    response = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments", json=environment("dev")
    )

    assert response.status_code == 409
    assert response.json()["code"] == "environment_exists"
    assert list(response.json()["errors"]) == ["environment"]


async def test_updating_an_environment(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    env = await create_environment(admin_client, service["id"], name="dev")

    response = await admin_client.put(
        f"/api/v1/services/{service['id']}/environments/{env['id']}",
        json=environment("dev", host="other.dev.internal", timeoutSeconds=5),
    )

    assert response.status_code == 200
    assert response.json()["baseUrl"] == "https://other.dev.internal"
    assert response.json()["timeoutSeconds"] == 5
    entry = (await audit_rows())[-1]
    assert entry.action is AuditAction.UPDATE
    assert set(entry.changes) == {"serviceId", "baseUrl", "timeoutSeconds"}


async def test_updating_an_environment_to_its_own_values_is_a_no_op(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    env = await create_environment(admin_client, service["id"], name="dev")

    response = await admin_client.put(
        f"/api/v1/services/{service['id']}/environments/{env['id']}", json=environment("dev")
    )

    assert response.status_code == 200
    assert response.json()["updatedAt"] == env["updatedAt"]
    assert len(await audit_rows()) == 2  # the two creates only


async def test_an_environment_can_not_be_renamed_onto_a_sibling(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    await create_environment(admin_client, service["id"], name="stage")
    dev = await create_environment(admin_client, service["id"], name="dev")

    response = await admin_client.put(
        f"/api/v1/services/{service['id']}/environments/{dev['id']}", json=environment("stage")
    )

    assert response.status_code == 409
    assert response.json()["code"] == "environment_exists"


async def test_an_environment_update_checks_the_allowlist(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    env = await create_environment(admin_client, service["id"])

    response = await admin_client.put(
        f"/api/v1/services/{service['id']}/environments/{env['id']}",
        json=environment(host="evil.example.com"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "upstream_host_not_allowed"


async def test_an_environment_of_another_service_is_404(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    first = await create_service(admin_client)
    second = await create_service(admin_client, name="other", pathPrefix="/other")
    env = await create_environment(admin_client, first["id"], name="dev")

    for method in ("PUT", "DELETE"):
        response = await admin_client.request(
            method,
            f"/api/v1/services/{second['id']}/environments/{env['id']}",
            json=environment("dev"),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


async def test_deleting_an_environment_removes_the_settings_that_chose_it(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await as_developer("root", is_admin=True)
    service = await create_service(admin_client)
    await create_environment(admin_client, service["id"], name="stage")
    dev = await create_environment(admin_client, service["id"], name="dev")
    async with session_factory() as session:
        session.add(
            DeveloperServiceSetting(
                developer_id=admin.id,
                service_id=uuid.UUID(service["id"]),
                service_environment_id=uuid.UUID(dev["id"]),
            )
        )
        await session.commit()

    response = await admin_client.delete(
        f"/api/v1/services/{service['id']}/environments/{dev['id']}"
    )

    assert response.status_code == 204
    async with session_factory() as session:
        assert (await session.scalars(select(DeveloperServiceSetting))).all() == []
    listed = (await admin_client.get("/api/v1/services")).json()[0]["environments"]
    assert [e["environment"] for e in listed] == ["stage"]


async def test_the_default_environment_can_not_be_deleted(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)  # default: stage
    stage = await create_environment(admin_client, service["id"], name="stage")

    response = await admin_client.delete(
        f"/api/v1/services/{service['id']}/environments/{stage['id']}"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert "default" in response.json()["errors"]["environment"][0]


async def test_the_panel_save_order_works(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    """The Panel saves the Service first, then deletes and creates environments (useSaveService)."""
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client, defaultEnvironment="stage")
    stage = await create_environment(admin_client, service["id"], name="stage")

    switched = await admin_client.put(
        f"/api/v1/services/{service['id']}", json={**SERVICE, "defaultEnvironment": "dev"}
    )  # `dev` doesn't exist yet
    deleted = await admin_client.delete(
        f"/api/v1/services/{service['id']}/environments/{stage['id']}"
    )
    created = await admin_client.post(
        f"/api/v1/services/{service['id']}/environments", json=environment("dev")
    )

    assert (switched.status_code, deleted.status_code, created.status_code) == (200, 204, 201)


async def test_environment_secrets_are_masked_in_the_audit_trail(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    """NFR-07: audit `changes` never hold a token, even one stored as an extra header."""
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    await create_environment(
        admin_client,
        service["id"],
        extraHeaders={"Authorization": "Bearer hunter2", "X-Api-Key": "k-123", "X-Team": "core"},
    )

    entry = (await audit_rows())[-1]
    assert entry.changes["extraHeaders"] == {
        "Authorization": "***",
        "X-Api-Key": "***",
        "X-Team": "core",
    }
    assert "hunter2" not in str(entry.changes)


async def test_catalog_writes_notify_with_catalog(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, listener: Listener
) -> None:
    await as_developer("root", is_admin=True)
    await listener.payloads(1)
    service = await create_service(admin_client)
    await listener.payloads(1)

    await create_environment(admin_client, service["id"])

    assert await listener.payloads(1) == ["catalog"]


# ---- parallel writes: the unique constraints decide, the loser gets a 409, never a 500 ----


async def test_parallel_creates_of_one_name_have_one_winner(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)

    responses = await asyncio.gather(
        *(
            admin_client.post("/api/v1/services", json={**SERVICE, "pathPrefix": f"/p{i}"})
            for i in range(6)
        )
    )

    assert sorted(r.status_code for r in responses) == [201] + [409] * 5
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"name_taken"}
    assert len((await admin_client.get("/api/v1/services")).json()) == 1


async def test_parallel_creates_of_one_prefix_have_one_winner(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)

    responses = await asyncio.gather(
        *(
            admin_client.post("/api/v1/services", json={**SERVICE, "name": f"svc{i}"})
            for i in range(6)
        )
    )

    assert sorted(r.status_code for r in responses) == [201] + [409] * 5
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"path_prefix_taken"}
    assert len((await admin_client.get("/api/v1/services")).json()) == 1


async def test_parallel_creates_of_one_environment_have_one_winner(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("root", is_admin=True)
    service = await create_service(admin_client)

    responses = await asyncio.gather(
        *(
            admin_client.post(
                f"/api/v1/services/{service['id']}/environments", json=environment("dev")
            )
            for _ in range(6)
        )
    )

    assert sorted(r.status_code for r in responses) == [201] + [409] * 5
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"environment_exists"}
