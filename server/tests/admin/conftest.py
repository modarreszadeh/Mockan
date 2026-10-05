"""Admin API fixtures: the app on the test database and `as_developer` (no real IdP, testing §3)."""

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.app import create_app
from mockan.admin.auth import current_developer
from mockan.admin.deps import SessionDep
from mockan.infrastructure.db.models import AuditLog, Developer
from mockan.infrastructure.settings import MockanSettings
from tests.infrastructure.helpers import make_developer

ALLOWED_HOSTS = ["identity.stage.internal", "*.dev.internal"]


@pytest.fixture(autouse=True)
def no_panel_build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests must not depend on a Panel build left in `admin/static/` by `npm run build:server`."""
    monkeypatch.setattr("mockan.admin.app.STATIC_DIR", tmp_path / "no-panel-build")


@pytest.fixture
def admin_settings(pg_container: str) -> MockanSettings:
    return MockanSettings(
        _env_file=None,  # type: ignore[call-arg]  # pydantic-settings init argument
        database_url=pg_container,
        auth_mode="dev",
        session_secret="x" * 40,
        allowed_upstream_hosts=ALLOWED_HOSTS,
        public_base_url="https://mock.test",
        admin_sso_subjects=["dev:root"],
    )


@pytest.fixture
def admin_app(
    admin_settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession]
) -> FastAPI:
    return create_app(admin_settings, session_factory)


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=admin_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://admin") as client:
        yield client


class AsDeveloper:
    """Create a Developer row and make every request act as them (overrides `current_developer`)."""

    def __init__(self, app: FastAPI, factory: async_sessionmaker[AsyncSession]) -> None:
        self._app = app
        self._factory = factory

    async def __call__(
        self, slug: str | None = "ehtesham", *, is_admin: bool = False, is_enabled: bool = True
    ) -> Developer:
        async with self._factory() as session:
            developer = make_developer(slug, is_admin=is_admin, is_enabled=is_enabled)
            session.add(developer)
            await session.commit()
        self.switch(developer)
        return developer

    def switch(self, developer: Developer) -> None:
        developer_id = developer.id

        async def current(session: SessionDep) -> Developer:
            found = await session.get(Developer, developer_id)
            assert found is not None
            return found

        self._app.dependency_overrides[current_developer] = current


@pytest.fixture
def as_developer(
    admin_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> AsDeveloper:
    return AsDeveloper(admin_app, session_factory)


@pytest.fixture
def audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[list[AuditLog]]]:
    """Every `audit_logs` row so far, oldest first."""

    async def fetch() -> list[AuditLog]:
        async with session_factory() as session:
            return list(await session.scalars(select(AuditLog).order_by(AuditLog.id)))

    return fetch
