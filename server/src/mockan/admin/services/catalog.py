"""Service catalog (admin only, D-08): Services and their ServiceEnvironments (PR-10, PR-15)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mockan.admin.problems import DomainError, not_found, validation_error
from mockan.admin.schemas.service import ServiceEnvironmentIn, ServiceIn
from mockan.admin.services.changes import diff
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.domain.errors import ErrorCode
from mockan.domain.validation import host_is_allowed
from mockan.infrastructure import audit
from mockan.infrastructure.db.errors import violated_constraint
from mockan.infrastructure.db.models import Developer, Service, ServiceEnvironment
from mockan.infrastructure.settings import MockanSettings


async def list_services(session: AsyncSession) -> list[Service]:
    result = await session.scalars(
        select(Service).options(selectinload(Service.environments)).order_by(Service.name)
    )
    return list(result)


async def get_service(session: AsyncSession, service_id: uuid.UUID) -> Service:
    service = await session.scalar(
        select(Service)
        .where(Service.id == service_id)
        .options(selectinload(Service.environments))
        .execution_options(populate_existing=True)  # never serve a stale copy after a rollback
    )
    if service is None:
        raise not_found("Service")
    return service


def _service_values(service: Service) -> dict[str, Any]:
    return {
        "name": service.name,
        "pathPrefix": service.path_prefix,
        "stripPrefix": service.strip_prefix,
        "rewriteOrigin": service.rewrite_origin,
        "defaultEnvironment": service.default_environment.value,
    }


def _environment_values(environment: ServiceEnvironment) -> dict[str, Any]:
    return {
        "environment": environment.environment.value,
        "baseUrl": environment.base_url,
        "timeoutSeconds": environment.timeout_seconds,
        "extraHeaders": environment.extra_headers,
    }


def _name_taken(name: str) -> DomainError:
    return DomainError(
        ErrorCode.NAME_TAKEN,
        409,
        "Service name already in use",
        errors={"name": [f"A Service named “{name}” already exists."]},
    )


def _prefix_taken(path_prefix: str) -> DomainError:
    return DomainError(
        ErrorCode.PATH_PREFIX_TAKEN,
        409,
        "Path prefix already in use",
        errors={"pathPrefix": [f"Path prefix {path_prefix} is already used by another Service."]},
    )


def _environment_exists(service_name: str, environment: str) -> DomainError:
    return DomainError(
        ErrorCode.ENVIRONMENT_EXISTS,
        409,
        "Environment already exists",
        errors={"environment": [f"{service_name} already has a {environment} environment."]},
    )


async def _ensure_unique(
    session: AsyncSession, name: str, path_prefix: str, exclude: uuid.UUID | None = None
) -> None:
    others = Service.id != exclude if exclude else Service.id.is_not(None)
    if await session.scalar(select(Service.id).where(others, Service.name == name)):
        raise _name_taken(name)
    # The unique index is case-sensitive; two prefixes differing only by case would still be one
    # route to a case-insensitive matcher (PR-04), so compare lowercased.
    if await session.scalar(
        select(Service.id).where(others, func.lower(Service.path_prefix) == path_prefix.lower())
    ):
        raise _prefix_taken(path_prefix)


@asynccontextmanager
async def _mapping_conflicts(
    session: AsyncSession, *, service_name: str, path_prefix: str = "", environment: str = ""
) -> AsyncIterator[None]:
    """Run the writes (flush and commit) inside; a unique race that slipped past the pre-checks
    becomes the same 409 the pre-checks give.

    The arguments are plain strings because a rollback expires every ORM object.
    """
    try:
        yield
    except IntegrityError as error:
        await session.rollback()
        match violated_constraint(error):
            case "uq_services_name":
                raise _name_taken(service_name) from error
            case "uq_services_path_prefix":
                raise _prefix_taken(path_prefix) from error
            case "uq_service_environments_service_id_environment":
                raise _environment_exists(service_name, environment) from error
        raise


async def create_service(session: AsyncSession, actor: Developer, data: ServiceIn) -> Service:
    await _ensure_unique(session, data.name, data.path_prefix)
    service = Service(
        name=data.name,
        path_prefix=data.path_prefix,
        strip_prefix=data.strip_prefix,
        rewrite_origin=data.rewrite_origin,
        default_environment=data.default_environment,
    )
    async with _mapping_conflicts(session, service_name=data.name, path_prefix=data.path_prefix):
        session.add(service)
        await session.flush()
        audit.record(
            session,
            actor,
            AuditAction.CREATE,
            AuditEntityType.SERVICE,
            service.id,
            _service_values(service),
        )
        service_id = service.id
        await session.commit()
    return await get_service(session, service_id)


async def update_service(
    session: AsyncSession, actor: Developer, service_id: uuid.UUID, data: ServiceIn
) -> Service:
    service = await get_service(session, service_id)
    await _ensure_unique(session, data.name, data.path_prefix, exclude=service.id)
    old = _service_values(service)
    service.name = data.name
    service.path_prefix = data.path_prefix
    service.strip_prefix = data.strip_prefix
    service.rewrite_origin = data.rewrite_origin
    # TODO(OQ-B6): `default_environment` is not required to exist among the environments here;
    # the Panel saves the Service before its environments. It is enforced when deleting one.
    service.default_environment = data.default_environment
    changes = diff(old, _service_values(service))
    if not changes:
        return service
    audit.record(session, actor, AuditAction.UPDATE, AuditEntityType.SERVICE, service.id, changes)
    async with _mapping_conflicts(session, service_name=data.name, path_prefix=data.path_prefix):
        await session.commit()
    return await get_service(session, service_id)


async def delete_service(session: AsyncSession, actor: Developer, service_id: uuid.UUID) -> None:
    service = await get_service(session, service_id)
    audit.record(
        session,
        actor,
        AuditAction.DELETE,
        AuditEntityType.SERVICE,
        service.id,
        _service_values(service),
    )
    await session.delete(service)  # environments and settings cascade in the database
    await session.commit()


# ---- ServiceEnvironments ----


def validate_base_url(base_url: str, settings: MockanSettings) -> str:
    """The URL stripped, if it is a plain http(s) URL on an allowlisted host (NFR-06, PR-15)."""
    value = base_url.strip()
    not_a_url = validation_error(
        {"baseUrl": ["Enter a full URL, e.g. https://limsa.dev.internal."]}
    )
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises ValueError for a malformed port
    except ValueError:
        raise not_a_url from None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise not_a_url
    if parts.username is not None or parts.password is not None:
        raise validation_error(
            {"baseUrl": ["Don't put credentials in the URL; use extra headers instead."]}
        )
    if parts.query or parts.fragment:
        raise validation_error({"baseUrl": ["Use a URL without a query string or fragment."]})
    if not host_is_allowed(parts.hostname, settings.allowed_upstream_hosts):
        raise DomainError(
            ErrorCode.UPSTREAM_HOST_NOT_ALLOWED,
            422,
            "Upstream host not allowed",
            "The base URL's host is not in MOCKAN_ALLOWED_UPSTREAM_HOSTS.",
            {"baseUrl": ["Only allowlisted dev/stage hosts can be used."]},
        )
    return value


def _find_environment(service: Service, environment_id: uuid.UUID) -> ServiceEnvironment:
    for environment in service.environments:
        if environment.id == environment_id:
            return environment
    raise not_found("ServiceEnvironment")


async def create_environment(
    session: AsyncSession,
    settings: MockanSettings,
    actor: Developer,
    service_id: uuid.UUID,
    data: ServiceEnvironmentIn,
) -> ServiceEnvironment:
    service = await get_service(session, service_id)
    base_url = validate_base_url(data.base_url, settings)
    if any(existing.environment == data.environment for existing in service.environments):
        raise _environment_exists(service.name, data.environment.value)
    environment = ServiceEnvironment(
        service_id=service.id,
        environment=data.environment,
        base_url=base_url,
        timeout_seconds=data.timeout_seconds,
        extra_headers=data.extra_headers,
    )
    async with _mapping_conflicts(
        session, service_name=service.name, environment=data.environment.value
    ):
        session.add(environment)
        await session.flush()
        audit.record(
            session,
            actor,
            AuditAction.CREATE,
            AuditEntityType.SERVICE_ENVIRONMENT,
            environment.id,
            {"serviceId": str(service.id), **_environment_values(environment)},
        )
        await session.commit()
    return environment


async def update_environment(
    session: AsyncSession,
    settings: MockanSettings,
    actor: Developer,
    service_id: uuid.UUID,
    environment_id: uuid.UUID,
    data: ServiceEnvironmentIn,
) -> ServiceEnvironment:
    service = await get_service(session, service_id)
    environment = _find_environment(service, environment_id)
    base_url = validate_base_url(data.base_url, settings)
    if data.environment != environment.environment and any(
        other.environment == data.environment for other in service.environments
    ):
        raise _environment_exists(service.name, data.environment.value)
    old = _environment_values(environment)
    environment.environment = data.environment
    environment.base_url = base_url
    environment.timeout_seconds = data.timeout_seconds
    environment.extra_headers = data.extra_headers
    changes = diff(old, _environment_values(environment))
    if not changes:
        return environment
    audit.record(
        session,
        actor,
        AuditAction.UPDATE,
        AuditEntityType.SERVICE_ENVIRONMENT,
        environment.id,
        {"serviceId": str(service.id), **changes},
    )
    async with _mapping_conflicts(
        session, service_name=service.name, environment=data.environment.value
    ):
        await session.commit()
    return environment


async def delete_environment(
    session: AsyncSession, actor: Developer, service_id: uuid.UUID, environment_id: uuid.UUID
) -> None:
    service = await get_service(session, service_id)
    environment = _find_environment(service, environment_id)
    # TODO(OQ-B6): deleting the default environment would leave every Developer without a
    # setting unresolvable (`service_not_resolved`), so the default must be changed first.
    if environment.environment == service.default_environment:
        raise validation_error(
            {
                "environment": [
                    f"{environment.environment.value} is the default environment of "
                    f"{service.name}. Choose another default first."
                ]
            }
        )
    audit.record(
        session,
        actor,
        AuditAction.DELETE,
        AuditEntityType.SERVICE_ENVIRONMENT,
        environment.id,
        {"serviceId": str(service.id), **_environment_values(environment)},
    )
    await session.delete(environment)
    await session.commit()
