"""`Developer` and `DeveloperUpdate` (`GET`/`PUT /me`)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from mockan.admin.schemas.base import CamelInput, CamelModel
from mockan.domain.constants import MAX_ALLOWED_ORIGINS, MAX_DISPLAY_NAME_LENGTH
from mockan.domain.validation import origin_problem
from mockan.infrastructure.db.models import Developer


def _display_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter your name.")
    if len(value) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"Use at most {MAX_DISPLAY_NAME_LENGTH} characters.")
    return value


def _origin(value: str) -> str:
    problem = origin_problem(value)
    if problem:
        raise ValueError(problem)
    return value.strip()


DisplayName = Annotated[str, AfterValidator(_display_name)]
Origin = Annotated[str, AfterValidator(_origin)]


class DeveloperOut(CamelModel):
    id: uuid.UUID
    slug: str | None
    display_name: str
    allowed_origins: list[str]
    is_enabled: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    public_base_url: str  # G-4: read-only, from MOCKAN_PUBLIC_BASE_URL

    @classmethod
    def of(cls, developer: Developer, public_base_url: str) -> DeveloperOut:
        return cls(
            id=developer.id,
            slug=developer.slug,
            display_name=developer.display_name,
            allowed_origins=developer.allowed_origins,
            is_enabled=developer.is_enabled,
            is_admin=developer.is_admin,
            created_at=developer.created_at,
            updated_at=developer.updated_at,
            public_base_url=public_base_url,
        )


class DeveloperUpdateIn(CamelInput):
    """Every field is optional; `null` means "leave it". `slug` can be set only once."""

    slug: str | None = None
    display_name: DisplayName | None = None
    allowed_origins: Annotated[list[Origin], Field(max_length=MAX_ALLOWED_ORIGINS)] | None = None
