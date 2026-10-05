"""`GET`/`PUT /me`: the current Developer's profile and slug (PR-01)."""

from fastapi import APIRouter

from mockan.admin.auth import CurrentDeveloper, WritableDeveloper
from mockan.admin.deps import SessionDep, SettingsDep
from mockan.admin.schemas.developer import DeveloperOut, DeveloperUpdateIn
from mockan.admin.schemas.problem import problems
from mockan.admin.services import developers

router = APIRouter(tags=["me"])


@router.get("/me", response_model=DeveloperOut, responses=problems(401))
async def get_me(developer: CurrentDeveloper, settings: SettingsDep) -> DeveloperOut:
    return DeveloperOut.of(developer, settings.public_base_url)


@router.put(
    "/me",
    response_model=DeveloperOut,
    responses=problems(401, 403, 409, 422),
)
async def update_me(
    update: DeveloperUpdateIn,
    developer: WritableDeveloper,
    session: SessionDep,
    settings: SettingsDep,
) -> DeveloperOut:
    updated = await developers.update_profile(session, developer, update)
    return DeveloperOut.of(updated, settings.public_base_url)
