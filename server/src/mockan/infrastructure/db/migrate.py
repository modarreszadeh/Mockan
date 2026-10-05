"""Run Alembic migrations from application code (`MOCKAN_MIGRATE_ON_STARTUP`, non-prod only)."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

# src/mockan/infrastructure/db/migrate.py -> server/
_SERVER_ROOT = Path(__file__).resolve().parents[4]


def _config(database_url: str) -> Config:
    ini = _SERVER_ROOT / "alembic.ini"
    if not ini.is_file():
        raise RuntimeError(
            f"Cannot migrate on startup: {ini} not found. Run `alembic upgrade head`."
        )
    config = Config(str(ini))
    config.set_main_option("script_location", str(_SERVER_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))  # ConfigParser
    return config


async def upgrade_to_head(database_url: str) -> None:
    """`alembic upgrade head`. `env.py` calls `asyncio.run`, so it runs in a worker thread."""
    await asyncio.to_thread(command.upgrade, _config(database_url), "head")
