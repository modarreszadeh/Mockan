"""Request-scoped dependencies: settings and the database session."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mockan.infrastructure.settings import MockanSettings


def get_settings(request: Request) -> MockanSettings:
    settings: MockanSettings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit explicitly; anything uncommitted is rolled back."""
    async with request.app.state.session_factory() as session:
        yield session


SettingsDep = Annotated[MockanSettings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
