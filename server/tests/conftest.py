"""Shared pytest configuration: markers (see pyproject.toml) and the PostgreSQL fixture."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

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
