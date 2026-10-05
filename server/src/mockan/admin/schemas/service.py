"""Service catalog and per-Developer environment choice (`/services*`, `/me/service-settings`)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StrictBool, StrictInt

from mockan.admin.schemas.base import CamelInput, CamelModel
from mockan.admin.schemas.common import check_headers
from mockan.domain.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_BASE_URL_LENGTH,
    MAX_EXTRA_HEADERS,
    MAX_PATH_PREFIX_LENGTH,
    MAX_SERVICE_NAME_LENGTH,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    PATH_PREFIX_REGEX,
    SERVICE_NAME_REGEX,
)
from mockan.domain.enums import EnvironmentName


def _name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a name.")
    if len(value) > MAX_SERVICE_NAME_LENGTH or SERVICE_NAME_REGEX.fullmatch(value) is None:
        raise ValueError("Use lowercase letters, digits and hyphens, e.g. limsa.")
    return value


def _path_prefix(value: str) -> str:
    value = value.strip()
    if len(value) > MAX_PATH_PREFIX_LENGTH or PATH_PREFIX_REGEX.fullmatch(value) is None:
        raise ValueError(
            "Start with “/” and don't end with “/”, e.g. /limsa. Just “/” matches every path."
        )
    return value


def _extra_headers(value: dict[str, str]) -> dict[str, str]:
    return check_headers(value, MAX_EXTRA_HEADERS)


class ServiceEnvironmentIn(CamelInput):
    environment: EnvironmentName
    base_url: Annotated[str, Field(max_length=MAX_BASE_URL_LENGTH)]
    timeout_seconds: Annotated[StrictInt, Field(ge=MIN_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS)] = (
        DEFAULT_TIMEOUT_SECONDS
    )
    extra_headers: Annotated[dict[str, str], AfterValidator(_extra_headers)] = Field(
        default_factory=dict
    )


class ServiceEnvironmentOut(CamelModel):
    id: uuid.UUID
    service_id: uuid.UUID
    environment: EnvironmentName
    base_url: str
    timeout_seconds: int
    extra_headers: dict[str, str]
    created_at: datetime
    updated_at: datetime


class ServiceIn(CamelInput):
    name: Annotated[str, AfterValidator(_name)]
    path_prefix: Annotated[str, AfterValidator(_path_prefix)]
    strip_prefix: StrictBool = False
    rewrite_origin: StrictBool = False
    default_environment: EnvironmentName = EnvironmentName.STAGE


class ServiceOut(CamelModel):
    id: uuid.UUID
    name: str
    path_prefix: str
    strip_prefix: bool
    rewrite_origin: bool
    default_environment: EnvironmentName
    environments: list[ServiceEnvironmentOut]
    created_at: datetime
    updated_at: datetime


class ServiceSettingIn(CamelInput):
    service_id: uuid.UUID
    service_environment_id: uuid.UUID


class ServiceSettingOut(CamelModel):
    service_id: uuid.UUID
    service_environment_id: uuid.UUID
