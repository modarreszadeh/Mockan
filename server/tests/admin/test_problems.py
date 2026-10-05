"""problem+json shapes of the Admin API: G-1 (`errors` map), G-5 codes, G-12 (JSON only)."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.infrastructure.db.models import Developer
from tests.admin.conftest import AsDeveloper

pytestmark = [pytest.mark.db, pytest.mark.req("PR-16")]


async def test_unauthenticated_request_gets_a_problem(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://mock.test/problems/unauthenticated",
        "title": "Sign in to continue",
        "status": 401,
        "code": "unauthenticated",
    }


async def test_unknown_route_is_a_not_found_problem(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/v1/nothing-here")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_wrong_method_is_a_problem_with_an_allow_header(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.delete("/api/v1/me")

    assert response.status_code == 405
    assert response.json()["status"] == 405
    assert "allow" in response.headers


async def test_validation_errors_are_a_camel_case_map(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put(
        "/api/v1/me", json={"displayName": "  ", "allowedOrigins": ["http://ok:*", "nope"]}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["errors"] == {
        "displayName": ["Enter your name."],
        "allowedOrigins.1": ["Start with http:// or https://."],
    }


async def test_unknown_fields_are_rejected(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put("/api/v1/me", json={"isAdmin": True})

    assert response.status_code == 422
    assert "isAdmin" in response.json()["errors"]


async def test_a_body_that_is_not_json_is_a_problem_with_a_detail(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.put(
        "/api/v1/me", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The request body isn't valid JSON."


async def test_writes_need_a_json_content_type(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """G-12: a cross-site HTML form can only send form/text types, so it can't write."""
    await as_developer(None)

    response = await admin_client.put(
        "/api/v1/me", content=b'{"slug": "sneaky"}', headers={"content-type": "text/plain"}
    )

    assert response.status_code == 422
    async with session_factory() as session:
        claimed = await session.scalar(
            select(func.count()).select_from(Developer).where(Developer.slug == "sneaky")
        )
    assert claimed == 0


async def test_a_malformed_id_is_a_404(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_admin=True)

    response = await admin_client.delete("/api/v1/services/not-a-uuid")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_an_unhandled_error_is_a_500_problem_without_internals(
    admin_app: object, as_developer: AsDeveloper
) -> None:
    from fastapi import FastAPI

    assert isinstance(admin_app, FastAPI)

    @admin_app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    transport = httpx.ASGITransport(app=admin_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/api/v1/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret internals" not in response.text
