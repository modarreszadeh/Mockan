"""Shared pytest configuration: markers (see pyproject.toml) and the PostgreSQL fixture."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from mockan.infrastructure.db import notify
from mockan.infrastructure.db.models import Base
from mockan.infrastructure.db.session import create_session_factory
from tests.support.notify_listener import Listener
from tests.support.snapshot_builder import SnapshotBuilder

SERVER_ROOT = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    config = Config(str(SERVER_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def pg_container() -> Iterator[str]:
    """A PostgreSQL 18 container with migrations applied. Yields an `postgresql+asyncpg://` URL."""
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        url = container.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture
def snapshot_builder() -> SnapshotBuilder:
    return SnapshotBuilder()


@pytest.fixture
async def engine(pg_container: str) -> AsyncIterator[AsyncEngine]:
    """An engine on the migrated test database; every table is emptied after the test."""
    engine = create_async_engine(pg_container)
    yield engine
    tables = ", ".join(f'"mockan"."{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions with Mockan's NOTIFY hook, like the Admin and the loader use."""
    return create_session_factory(engine)


@pytest.fixture
async def listener(pg_container: str, engine: AsyncEngine) -> AsyncIterator[Listener]:
    """Collects the `mockan_config_changed` payloads sent while the test runs."""
    connection = await asyncpg.connect(pg_container.replace("+asyncpg", ""))
    listener = Listener()
    await connection.add_listener(notify.CHANNEL, listener)
    yield listener
    await connection.close()


@pytest.fixture(autouse=True)
def _fresh_structlog() -> None:
    """An app lifespan in an earlier test points structlog at that test's captured stdout, which is
    closed by the time a later test logs; start every test from structlog's defaults."""
    structlog.reset_defaults()
