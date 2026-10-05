"""Async Alembic environment: schema `mockan`, version table inside that schema."""

import asyncio
import os

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from mockan.infrastructure.db.models import SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    # Tests and tooling can set it with Config.set_main_option("sqlalchemy.url", ...).
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("MOCKAN_DATABASE_URL")
    if not url:
        raise RuntimeError("Set MOCKAN_DATABASE_URL (or sqlalchemy.url) to run migrations.")
    return url


def _include_name(name: str | None, type_: str, _parent_names: object) -> bool:
    # Autogenerate must only look at schema `mockan`, never at `public` or system schemas.
    return name == SCHEMA if type_ == "schema" else True


def _configure(connection: Connection | None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=_include_name,
        compare_type=True,
    )


def _run_sync_migrations(connection: Connection) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
    finally:
        await engine.dispose()


def run_migrations_offline() -> None:
    _configure(None, url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())
