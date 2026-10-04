"""Proves the Testcontainers + Alembic wiring works (B0 exit); needs Docker."""

import asyncpg
import pytest


@pytest.mark.db
async def test_pg_container_has_mockan_schema(pg_container: str) -> None:
    connection = await asyncpg.connect(pg_container.replace("+asyncpg", ""))
    try:
        schema = await connection.fetchval(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'mockan'"
        )
    finally:
        await connection.close()
    assert schema == "mockan"
