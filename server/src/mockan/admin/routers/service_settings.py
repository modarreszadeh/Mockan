"""`GET`/`PUT /me/service-settings`: the Developer's environment per Service (FR-04)."""

from fastapi import APIRouter

from mockan.admin.auth import CurrentDeveloper, WritableDeveloper
from mockan.admin.deps import SessionDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.service import ServiceSettingIn, ServiceSettingOut
from mockan.admin.services import service_settings

router = APIRouter(prefix="/me/service-settings", tags=["service-settings"])


@router.get("", response_model=list[ServiceSettingOut], responses=problems(401))
async def list_service_settings(
    developer: CurrentDeveloper, session: SessionDep
) -> list[ServiceSettingOut]:
    rows = await service_settings.list_settings(session, developer)
    return [ServiceSettingOut.model_validate(row) for row in rows]


@router.put("", response_model=list[ServiceSettingOut], responses=problems(401, 403, 422))
async def replace_service_settings(
    items: list[ServiceSettingIn], developer: WritableDeveloper, session: SessionDep
) -> list[ServiceSettingOut]:
    """Replace the whole set. A Service that is absent uses its default environment."""
    rows = await service_settings.replace_settings(session, developer, items)
    return [ServiceSettingOut.model_validate(row) for row in rows]
