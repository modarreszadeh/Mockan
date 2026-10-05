"""`GET`/`PUT /me`: profile, the claim-once slug (PR-01), allowed origins (PR-03)."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.problems import DomainError
from mockan.admin.schemas.developer import DeveloperUpdateIn
from mockan.admin.services import developers
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.domain.errors import ErrorCode
from mockan.infrastructure.db.models import AuditLog
from tests.admin.conftest import AsDeveloper
from tests.infrastructure.helpers import make_developer
from tests.support.notify_listener import Listener

pytestmark = [pytest.mark.db, pytest.mark.req("PR-01")]

AuditRows = Callable[[], Awaitable[list[AuditLog]]]


async def test_get_me_returns_the_panel_contract(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    developer = await as_developer("ehtesham")

    response = await admin_client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "slug",
        "displayName",
        "allowedOrigins",
        "isEnabled",
        "isAdmin",
        "createdAt",
        "updatedAt",
        "publicBaseUrl",
    }
    assert body["id"] == str(developer.id)
    assert body["slug"] == "ehtesham"
    assert body["publicBaseUrl"] == "https://mock.test"  # G-4
    assert body["createdAt"].endswith("Z")


async def test_claiming_a_slug_sets_it_and_audits_and_notifies(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    audit_rows: AuditRows,
    listener: Listener,
) -> None:
    developer = await as_developer(None)

    response = await admin_client.put("/api/v1/me", json={"slug": "ehtesham"})

    assert response.status_code == 200
    assert response.json()["slug"] == "ehtesham"
    assert (await admin_client.get("/api/v1/me")).json()["slug"] == "ehtesham"
    (entry,) = await audit_rows()
    assert (entry.action, entry.entity_type) == (AuditAction.UPDATE, AuditEntityType.DEVELOPER)
    assert entry.developer_id == developer.id
    assert entry.changes == {"slug": {"from": None, "to": "ehtesham"}}
    # One notification for creating the fixture row, one for the claim; both name the Developer.
    assert await listener.payloads(2) == [str(developer.id)] * 2


async def test_the_slug_can_only_be_set_once(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"slug": "another"})

    assert response.status_code == 409
    assert response.json()["code"] == "slug_immutable"
    assert "slug" in response.json()["errors"]


async def test_sending_the_current_slug_again_is_fine(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"slug": "ehtesham"})

    assert response.status_code == 200
    assert await audit_rows() == []  # nothing changed, so nothing is audited


@pytest.mark.parametrize(
    ("slug", "message"),
    [
        ("_mockan", "Slugs starting with “_” are reserved for Mockan."),
        ("api", "“api” is reserved. Pick another slug."),
        ("hubs", "“hubs” is reserved. Pick another slug."),
        ("health", "“health” is reserved. Pick another slug."),
        ("Ehtesham", "Use lowercase letters only."),
        ("1abc", "Start with a lowercase letter."),
        ("a", "Use at least 2 characters."),
        ("a" * 33, "Use at most 32 characters."),
        ("has space", "Use only lowercase letters, digits and hyphens."),
        ("under_score", "Use only lowercase letters, digits and hyphens."),
        ("", "Enter a slug."),
    ],
)
async def test_invalid_slugs_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, slug: str, message: str
) -> None:
    await as_developer(None)

    response = await admin_client.put("/api/v1/me", json={"slug": slug})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert response.json()["errors"] == {"slug": [message]}


async def test_a_taken_slug_is_409(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    await as_developer(None)

    response = await admin_client.put("/api/v1/me", json={"slug": "ehtesham"})

    assert response.status_code == 409
    assert response.json()["code"] == "slug_taken"


async def test_parallel_claims_of_one_slug_have_one_winner(
    admin_settings: object, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The DB unique constraint decides the race; the loser gets `slug_taken`, never a 500."""
    async with session_factory() as session:
        contenders = [make_developer(None) for _ in range(8)]
        session.add_all(contenders)
        await session.commit()

    async def claim(developer_id: object) -> str:
        async with session_factory() as session:
            developer = await developers.get_by_id(session, developer_id)  # type: ignore[arg-type]
            assert developer is not None
            try:
                await developers.update_profile(session, developer, DeveloperUpdateIn(slug="race"))
            except DomainError as error:
                assert error.code is ErrorCode.SLUG_TAKEN
                return "lost"
            return "won"

    outcomes = await asyncio.gather(*(claim(d.id) for d in contenders))

    assert sorted(outcomes) == ["lost"] * 7 + ["won"]


async def test_display_name_and_origins_can_be_updated_separately(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, audit_rows: AuditRows
) -> None:
    await as_developer("ehtesham")

    renamed = await admin_client.put("/api/v1/me", json={"displayName": "  Ehtesham R.  "})
    assert renamed.json()["displayName"] == "Ehtesham R."
    assert renamed.json()["allowedOrigins"] == ["http://localhost:*"]

    origins = ["https://app.dev.internal", "http://localhost:5173"]
    updated = await admin_client.put("/api/v1/me", json={"allowedOrigins": origins})
    assert updated.json()["allowedOrigins"] == origins
    assert updated.json()["displayName"] == "Ehtesham R."
    assert [e.changes.keys() for e in await audit_rows()] == [
        {"displayName"},
        {"allowedOrigins"},
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "localhost:3000",
        "ftp://localhost",
        "http://local host",
        "http://localhost/",
        "http://localhost:3000/app",
        "http://",
        "http://*:3000",
    ],
)
async def test_invalid_origins_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, origin: str
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"allowedOrigins": [origin]})

    assert response.status_code == 422
    assert list(response.json()["errors"]) == ["allowedOrigins.0"]


async def test_too_many_origins_is_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put(
        "/api/v1/me", json={"allowedOrigins": [f"http://h{i}.dev.internal" for i in range(51)]}
    )

    assert response.status_code == 422
    assert "allowedOrigins" in response.json()["errors"]


async def test_a_display_name_has_a_maximum_length(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"displayName": "n" * 101})

    assert response.status_code == 422
    assert response.json()["errors"] == {"displayName": ["Use at most 100 characters."]}


async def test_an_empty_origin_list_is_allowed(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"allowedOrigins": []})

    assert response.status_code == 200
    assert response.json()["allowedOrigins"] == []


async def test_a_developer_cannot_change_their_own_flags(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    for field in ("isAdmin", "isEnabled", "id", "developerId", "ssoSubject"):
        response = await admin_client.put("/api/v1/me", json={field: True})
        assert response.status_code == 422, field
    assert (await admin_client.get("/api/v1/me")).json()["isAdmin"] is False


async def test_updating_me_never_touches_another_developer(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    alice = await as_developer("alice")
    await as_developer("bob")

    await admin_client.put("/api/v1/me", json={"displayName": "Bob B."})

    as_developer.switch(alice)
    me = (await admin_client.get("/api/v1/me")).json()
    assert (me["slug"], me["displayName"]) == ("alice", "Alice")
