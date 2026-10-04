"""`/me/service-settings`: the Developer's environment per Service (FR-04, PR-04)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import create_environment, create_service
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-04")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]


class Catalog:
    """Two Services, each with a `dev` and a `stage` environment."""

    def __init__(self, services: dict[str, dict[str, Any]]) -> None:
        self.services = services

    def setting(self, service: str, environment: str) -> dict[str, str]:
        found = self.services[service]
        env = next(e for e in found["environments"] if e["environment"] == environment)
        return {"serviceId": found["id"], "serviceEnvironmentId": env["id"]}


@pytest.fixture
async def catalog(admin_client: httpx.AsyncClient, as_developer: AsDeveloper) -> Catalog:
    await as_developer("root", is_admin=True)
    services: dict[str, dict[str, Any]] = {}
    for name in ("limsa", "identity"):
        service = await create_service(admin_client, name=name, pathPrefix=f"/{name}")
        service["environments"] = [
            await create_environment(
                admin_client, service["id"], name=env, host=f"{name}.dev.internal"
            )
            for env in ("dev", "stage")
        ]
        services[name] = service
    return Catalog(services)


async def test_a_new_developer_has_no_settings(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.get("/api/v1/me/service-settings")

    assert response.status_code == 200
    assert response.json() == []


async def test_putting_settings_replaces_the_set(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    catalog: Catalog,
    audit_rows: AuditRows,
) -> None:
    developer = await as_developer("ehtesham")

    first = await admin_client.put(
        "/api/v1/me/service-settings",
        json=[catalog.setting("limsa", "dev"), catalog.setting("identity", "stage")],
    )
    assert first.status_code == 200
    assert {(s["serviceId"], s["serviceEnvironmentId"]) for s in first.json()} == {
        (s["serviceId"], s["serviceEnvironmentId"])
        for s in (catalog.setting("limsa", "dev"), catalog.setting("identity", "stage"))
    }

    second = await admin_client.put(
        "/api/v1/me/service-settings", json=[catalog.setting("limsa", "stage")]
    )
    assert second.json() == [catalog.setting("limsa", "stage")]
    assert (await admin_client.get("/api/v1/me/service-settings")).json() == second.json()

    cleared = await admin_client.put("/api/v1/me/service-settings", json=[])
    assert cleared.json() == []

    entries = [
        e for e in await audit_rows() if e.entity_type is AuditEntityType.DEVELOPER_SERVICE_SETTING
    ]
    assert [e.action for e in entries] == [AuditAction.UPDATE] * 3
    assert all(e.entity_id == str(developer.id) for e in entries)
    assert entries[0].changes["settings"]["from"] == {}


async def test_changing_one_service_keeps_the_others(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")
    await admin_client.put(
        "/api/v1/me/service-settings",
        json=[catalog.setting("limsa", "dev"), catalog.setting("identity", "dev")],
    )

    response = await admin_client.put(
        "/api/v1/me/service-settings",
        json=[catalog.setting("limsa", "stage"), catalog.setting("identity", "dev")],
    )

    by_service = {s["serviceId"]: s["serviceEnvironmentId"] for s in response.json()}
    assert by_service == {
        catalog.setting("limsa", "stage")["serviceId"]: catalog.setting("limsa", "stage")[
            "serviceEnvironmentId"
        ],
        catalog.setting("identity", "dev")["serviceId"]: catalog.setting("identity", "dev")[
            "serviceEnvironmentId"
        ],
    }


async def test_putting_the_same_set_again_writes_nothing(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    catalog: Catalog,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    await as_developer("ehtesham")
    body = [catalog.setting("limsa", "dev")]
    await admin_client.put("/api/v1/me/service-settings", json=body)
    audit_count = len(await audit_rows())
    await listener.payloads(1)
    listener.received.clear()

    response = await admin_client.put("/api/v1/me/service-settings", json=body)

    assert response.status_code == 200
    assert response.json() == body
    assert len(await audit_rows()) == audit_count
    assert await listener.nothing() == []


async def test_a_change_notifies_with_the_developer_id(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    catalog: Catalog,
    listener: Listener,
) -> None:
    developer = await as_developer("ehtesham")
    await listener.payloads(2)  # catalog setup + the fixture row
    listener.received.clear()

    await admin_client.put("/api/v1/me/service-settings", json=[catalog.setting("limsa", "dev")])

    assert await listener.payloads(1) == [str(developer.id)]


async def test_an_environment_of_another_service_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")
    mismatched = {
        "serviceId": catalog.setting("limsa", "dev")["serviceId"],
        "serviceEnvironmentId": catalog.setting("identity", "dev")["serviceEnvironmentId"],
    }

    response = await admin_client.put(
        "/api/v1/me/service-settings", json=[catalog.setting("identity", "dev"), mismatched]
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert list(response.json()["errors"]) == ["1.serviceEnvironmentId"]
    assert (await admin_client.get("/api/v1/me/service-settings")).json() == []


async def test_unknown_service_and_environment_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put(
        "/api/v1/me/service-settings",
        json=[{"serviceId": str(uuid.uuid4()), "serviceEnvironmentId": str(uuid.uuid4())}],
    )

    assert response.status_code == 422
    assert list(response.json()["errors"]) == ["0.serviceId"]


async def test_a_service_listed_twice_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put(
        "/api/v1/me/service-settings",
        json=[catalog.setting("limsa", "dev"), catalog.setting("limsa", "stage")],
    )

    assert response.status_code == 422
    assert list(response.json()["errors"]) == ["1.serviceId"]


async def test_the_body_must_be_a_list_of_settings(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham")

    for body in ({}, [{"serviceId": "x"}], [{**catalog.setting("limsa", "dev"), "extra": 1}]):
        response = await admin_client.put("/api/v1/me/service-settings", json=body)
        assert response.status_code == 422, body


async def test_settings_belong_to_one_developer(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    alice = await as_developer("alice")
    await admin_client.put("/api/v1/me/service-settings", json=[catalog.setting("limsa", "dev")])
    await as_developer("bob")

    assert (await admin_client.get("/api/v1/me/service-settings")).json() == []
    await admin_client.put("/api/v1/me/service-settings", json=[catalog.setting("limsa", "stage")])

    as_developer.switch(alice)
    assert (await admin_client.get("/api/v1/me/service-settings")).json() == [
        catalog.setting("limsa", "dev")
    ]


async def test_a_disabled_developer_can_read_but_not_write_settings(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, catalog: Catalog
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    assert (await admin_client.get("/api/v1/me/service-settings")).status_code == 200
    write = await admin_client.put("/api/v1/me/service-settings", json=[])
    assert write.status_code == 403
    assert write.json()["code"] == "developer_disabled"


async def test_settings_need_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/v1/me/service-settings")).status_code == 401
    assert (await admin_client.put("/api/v1/me/service-settings", json=[])).status_code == 401
