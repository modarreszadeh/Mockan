"""The built Panel is served by the Admin with an SPA fallback (G-11, OQ-03)."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.app import create_app
from mockan.admin.spa import normalise_base_path
from mockan.infrastructure.settings import MockanSettings

pytestmark = pytest.mark.db

INDEX = "<!doctype html><title>Mockan</title>"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets" / "app-123.js").write_text("console.log('hi')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside")
    return tmp_path


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://admin")


@pytest.fixture
def panel_app(
    admin_settings: MockanSettings,
    session_factory: async_sessionmaker[AsyncSession],
    static_dir: Path,
) -> FastAPI:
    return create_app(admin_settings, session_factory, static_dir=static_dir)


async def test_the_root_and_deep_links_serve_the_app_shell(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        for path in ("/", "/rules", "/rules/42/edit", "/services/"):
            response = await client.get(path)
            assert response.status_code == 200, path
            assert response.text == INDEX
            assert response.headers["cache-control"] == "no-cache"


async def test_static_files_are_served_as_they_are(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        asset = await client.get("/assets/app-123.js")
        icon = await client.get("/favicon.svg")

    assert asset.status_code == 200
    assert asset.text == "console.log('hi')"
    assert "javascript" in asset.headers["content-type"]
    assert icon.text == "<svg/>"


async def test_a_missing_asset_is_a_404_not_the_app_shell(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        response = await client.get("/assets/missing.js")

    assert response.status_code == 404


async def test_unknown_api_paths_are_problems_not_the_app_shell(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        for path in ("/api/v1/nothing", "/api/other", "/hubs/request-log"):
            response = await client.get(path)
            assert response.status_code == 404, path
            assert response.headers["content-type"] == "application/problem+json"
            assert response.json()["code"] == "not_found"


async def test_the_api_still_works_next_to_the_panel(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        response = await client.get("/api/v1/me")

    assert response.status_code == 401  # a real route, not the fallback


async def test_paths_can_not_escape_the_static_folder(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"):
            response = await client.get(path)
            assert "outside" not in response.text, path


async def test_a_nul_byte_in_the_path_is_a_404(panel_app: FastAPI) -> None:
    async with client_for(panel_app) as client:
        response = await client.get("/assets/%00")

    assert response.status_code == 404


async def test_the_panel_can_live_under_a_base_path(
    admin_settings: MockanSettings,
    session_factory: async_sessionmaker[AsyncSession],
    static_dir: Path,
) -> None:
    settings = admin_settings.model_copy(update={"panel_base_path": "/_mockan/admin/"})
    app = create_app(settings, session_factory, static_dir=static_dir)

    async with client_for(app) as client:
        assert (await client.get("/_mockan/admin")).text == INDEX
        assert (await client.get("/_mockan/admin/")).text == INDEX
        assert (await client.get("/_mockan/admin/rules")).text == INDEX
        assert (await client.get("/_mockan/admin/assets/app-123.js")).status_code == 200
        assert (await client.get("/")).status_code == 404  # outside the base path
        assert (await client.get("/api/v1/me")).status_code == 401
        login = await client.get("/api/v1/auth/login")
        assert login.headers["location"] == "/_mockan/admin/"  # sign-in lands on the Panel


async def test_without_a_build_there_is_no_panel(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/", "/"),
        ("", "/"),
        ("  ", "/"),
        ("/panel", "/panel"),
        ("panel/", "/panel"),
        ("//a//", "/a"),
    ],
)
def test_base_paths_are_normalised(raw: str, expected: str) -> None:
    assert normalise_base_path(raw) == expected
