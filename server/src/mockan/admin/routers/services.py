"""Service catalog: read for everyone, writes for admins (D-08, PR-10, PR-15)."""

import uuid

from fastapi import APIRouter, Response

from mockan.admin.auth import AdminDeveloper, CurrentDeveloper
from mockan.admin.deps import SessionDep, SettingsDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.service import (
    ServiceEnvironmentIn,
    ServiceEnvironmentOut,
    ServiceIn,
    ServiceOut,
)
from mockan.admin.services import catalog

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[ServiceOut], responses=problems(401))
async def list_services(_developer: CurrentDeveloper, session: SessionDep) -> list[ServiceOut]:
    return [ServiceOut.model_validate(s) for s in await catalog.list_services(session)]


@router.post("", status_code=201, response_model=ServiceOut, responses=problems(401, 403, 409, 422))
async def create_service(data: ServiceIn, admin: AdminDeveloper, session: SessionDep) -> ServiceOut:
    return ServiceOut.model_validate(await catalog.create_service(session, admin, data))


@router.put("/{service_id}", response_model=ServiceOut, responses=problems(401, 403, 404, 409, 422))
async def update_service(
    service_id: uuid.UUID, data: ServiceIn, admin: AdminDeveloper, session: SessionDep
) -> ServiceOut:
    return ServiceOut.model_validate(await catalog.update_service(session, admin, service_id, data))


@router.delete("/{service_id}", status_code=204, responses=problems(401, 403, 404))
async def delete_service(
    service_id: uuid.UUID, admin: AdminDeveloper, session: SessionDep
) -> Response:
    await catalog.delete_service(session, admin, service_id)
    return Response(status_code=204)


@router.post(
    "/{service_id}/environments",
    status_code=201,
    response_model=ServiceEnvironmentOut,
    responses=problems(401, 403, 404, 409, 422),
)
async def create_environment(
    service_id: uuid.UUID,
    data: ServiceEnvironmentIn,
    admin: AdminDeveloper,
    session: SessionDep,
    settings: SettingsDep,
) -> ServiceEnvironmentOut:
    environment = await catalog.create_environment(session, settings, admin, service_id, data)
    return ServiceEnvironmentOut.model_validate(environment)


@router.put(
    "/{service_id}/environments/{environment_id}",
    response_model=ServiceEnvironmentOut,
    responses=problems(401, 403, 404, 409, 422),
)
async def update_environment(
    service_id: uuid.UUID,
    environment_id: uuid.UUID,
    data: ServiceEnvironmentIn,
    admin: AdminDeveloper,
    session: SessionDep,
    settings: SettingsDep,
) -> ServiceEnvironmentOut:
    environment = await catalog.update_environment(
        session, settings, admin, service_id, environment_id, data
    )
    return ServiceEnvironmentOut.model_validate(environment)


@router.delete(
    "/{service_id}/environments/{environment_id}",
    status_code=204,
    responses=problems(401, 403, 404, 422),
)
async def delete_environment(
    service_id: uuid.UUID, environment_id: uuid.UUID, admin: AdminDeveloper, session: SessionDep
) -> Response:
    await catalog.delete_environment(session, admin, service_id, environment_id)
    return Response(status_code=204)
