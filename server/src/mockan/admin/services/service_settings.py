"""A Developer's environment choice per Service (FR-04, PR-04). No row = the Service default."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mockan.admin.problems import validation_error
from mockan.admin.schemas.service import ServiceSettingIn
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure import audit
from mockan.infrastructure.db.models import (
    Developer,
    DeveloperServiceSetting,
    Service,
    ServiceEnvironment,
)


async def list_settings(
    session: AsyncSession, developer: Developer
) -> list[DeveloperServiceSetting]:
    result = await session.scalars(
        select(DeveloperServiceSetting)
        .where(DeveloperServiceSetting.developer_id == developer.id)
        .order_by(DeveloperServiceSetting.service_id)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def _validate(session: AsyncSession, items: list[ServiceSettingIn]) -> None:
    errors: dict[str, list[str]] = {}
    seen: set[uuid.UUID] = set()
    for index, item in enumerate(items):
        if item.service_id in seen:
            errors[f"{index}.serviceId"] = ["This Service is listed twice."]
        seen.add(item.service_id)

    known_services = set(await session.scalars(select(Service.id).where(Service.id.in_(seen))))
    rows = await session.execute(
        select(ServiceEnvironment.id, ServiceEnvironment.service_id).where(
            ServiceEnvironment.id.in_({item.service_environment_id for item in items})
        )
    )
    owner_of = {row.id: row.service_id for row in rows}
    for index, item in enumerate(items):
        if item.service_id not in known_services:
            errors.setdefault(f"{index}.serviceId", ["Unknown Service."])
        elif owner_of.get(item.service_environment_id) != item.service_id:
            errors[f"{index}.serviceEnvironmentId"] = [
                "This environment doesn't belong to the Service."
            ]
    if errors:
        raise validation_error(errors)


async def replace_settings(
    session: AsyncSession, developer: Developer, items: list[ServiceSettingIn]
) -> list[DeveloperServiceSetting]:
    """Replace the whole set (PUT semantics). Nothing is written when nothing changes."""
    await _validate(session, items)
    existing = {row.service_id: row for row in await list_settings(session, developer)}
    wanted = {item.service_id: item.service_environment_id for item in items}

    before = {str(service): str(row.service_environment_id) for service, row in existing.items()}
    after = {str(service): str(environment) for service, environment in wanted.items()}
    if before == after:
        return list(existing.values())

    for service_id, row in existing.items():
        if service_id not in wanted:
            await session.delete(row)
        elif row.service_environment_id != wanted[service_id]:
            row.service_environment_id = wanted[service_id]
    for service_id, environment_id in wanted.items():
        if service_id not in existing:
            session.add(
                DeveloperServiceSetting(
                    developer_id=developer.id,
                    service_id=service_id,
                    service_environment_id=environment_id,
                )
            )
    audit.record(
        session,
        developer,
        AuditAction.UPDATE,
        AuditEntityType.DEVELOPER_SERVICE_SETTING,
        developer.id,
        {"settings": {"from": before, "to": after}},
    )
    await session.commit()
    return await list_settings(session, developer)
