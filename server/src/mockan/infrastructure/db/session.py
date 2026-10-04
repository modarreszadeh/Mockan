"""Async engine and session factory. Every session fires the NOTIFY hook (see `notify.py`)."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mockan.infrastructure.db.notify import NotifySession
from mockan.infrastructure.settings import MockanSettings


def create_engine(settings: MockanSettings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, sync_session_class=NotifySession)
