"""Sign-in in dev mode (G-9), sessions, first-login upsert and admin bootstrap."""

import asyncio
import json
from base64 import b64encode
from collections.abc import Awaitable, Callable

import httpx
import pytest
from itsdangerous import TimestampSigner
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.services import developers
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog, Developer
from mockan.infrastructure.settings import MockanSettings
from tests.admin.conftest import AsDeveloper
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-01")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]


async def test_dev_login_creates_the_developer_and_a_session(
    admin_client: httpx.AsyncClient, audit_rows: AuditRows
) -> None:
    login = await admin_client.get("/api/v1/auth/login", params={"as": "alice"})

    assert login.status_code == 303
    assert login.headers["location"] == "/"
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie  # dev mode runs over plain http

    me = await admin_client.get("/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert body["displayName"] == "alice"
    assert body["slug"] is None
    assert body["isAdmin"] is False
    assert body["isEnabled"] is True
    assert body["allowedOrigins"] == ["http://localhost:*", "http://127.0.0.1:*"]

    (entry,) = await audit_rows()
    assert (entry.action, entry.entity_type) == (AuditAction.CREATE, AuditEntityType.DEVELOPER)


async def test_login_twice_is_the_same_developer(
    admin_client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "alice"})
    first = (await admin_client.get("/api/v1/me")).json()["id"]
    await admin_client.get("/api/v1/auth/login", params={"as": "alice"})
    second = (await admin_client.get("/api/v1/me")).json()["id"]

    assert first == second
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Developer)) == 1


async def test_dev_login_can_sign_in_as_an_admin(admin_client: httpx.AsyncClient) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "boss", "admin": "1"})

    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is True


async def test_admin_bootstrap_list_applies_on_first_login(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "root"})  # subject dev:root

    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is True


async def test_a_later_login_promotes_but_never_demotes(
    admin_client: httpx.AsyncClient, audit_rows: AuditRows
) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "dana"})
    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is False

    await admin_client.get("/api/v1/auth/login", params={"as": "dana", "admin": "1"})
    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is True

    await admin_client.get("/api/v1/auth/login", params={"as": "dana"})
    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is True
    assert [e.action for e in await audit_rows()] == [AuditAction.CREATE, AuditAction.UPDATE]


async def test_the_bare_login_signs_in_as_dev(admin_client: httpx.AsyncClient) -> None:
    await admin_client.get("/api/v1/auth/login")

    assert (await admin_client.get("/api/v1/me")).json()["displayName"] == "dev"


async def test_dev_login_rejects_odd_names(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/v1/auth/login", params={"as": "a b/../c"})

    assert response.status_code == 422


async def test_logout_ends_the_session(admin_client: httpx.AsyncClient) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "alice"})

    assert (await admin_client.post("/api/v1/auth/logout")).status_code == 204
    assert (await admin_client.get("/api/v1/me")).status_code == 401


async def test_logout_without_a_session_is_fine(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.post("/api/v1/auth/logout")).status_code == 204


async def test_a_session_for_a_deleted_developer_is_unauthenticated(
    admin_client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "alice"})
    async with session_factory() as session:
        developer = await session.scalar(select(Developer))
        assert developer is not None
        await session.delete(developer)
        await session.commit()

    assert (await admin_client.get("/api/v1/me")).status_code == 401


async def test_a_signed_session_with_a_garbage_id_is_unauthenticated(
    admin_client: httpx.AsyncClient, admin_settings: MockanSettings
) -> None:
    """Only the server signs cookies, but a bad value (e.g. after a code change) must be a 401."""
    payload = b64encode(json.dumps({"developer_id": "not-a-uuid"}).encode())
    cookie = TimestampSigner(admin_settings.session_secret).sign(payload).decode()
    admin_client.cookies.set("mockan_session", cookie)

    assert (await admin_client.get("/api/v1/me")).status_code == 401


async def test_a_tampered_cookie_is_ignored(admin_client: httpx.AsyncClient) -> None:
    admin_client.cookies.set("mockan_session", "eyJkZXZlbG9wZXJfaWQiOiJ4In0.bad.sig")

    assert (await admin_client.get("/api/v1/me")).status_code == 401


async def test_the_callback_does_not_exist_in_dev_mode(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/v1/auth/callback")).status_code == 404


async def test_a_bearer_token_is_not_accepted_without_oidc(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/v1/me", headers={"authorization": "Bearer abc.def.ghi"})

    assert response.status_code == 401


async def test_a_disabled_developer_can_read_but_not_write(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    me = await admin_client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["isEnabled"] is False

    write = await admin_client.put("/api/v1/me", json={"displayName": "Still me"})
    assert write.status_code == 403
    assert write.json()["code"] == "developer_disabled"


async def test_parallel_first_logins_create_one_developer(
    admin_settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Parallel bearer-token calls from a new user all hit the first-login upsert at once."""

    async def sign_in() -> Developer:
        async with session_factory() as session:
            return await developers.sign_in(
                session, admin_settings, subject="oidc|new", display_name="New"
            )

    results = await asyncio.gather(*(sign_in() for _ in range(8)))

    assert len({developer.id for developer in results}) == 1
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Developer)) == 1


async def test_the_first_login_notifies_the_gateways(
    admin_client: httpx.AsyncClient, listener: Listener
) -> None:
    await admin_client.get("/api/v1/auth/login", params={"as": "alice"})
    developer_id = (await admin_client.get("/api/v1/me")).json()["id"]

    assert await listener.payloads(1) == [developer_id]
