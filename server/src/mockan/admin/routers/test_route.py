"""`POST /me/test-route`: which rule would answer, or where would it be forwarded (FR-10)."""

from fastapi import APIRouter

from mockan.admin.auth import CurrentDeveloper
from mockan.admin.deps import SessionDep, SettingsDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.test_route import TestRouteIn, TestRouteOut
from mockan.admin.services import test_route

router = APIRouter(prefix="/me/test-route", tags=["test-route"])


@router.post("", response_model=TestRouteOut, responses=problems(401, 422))
async def run_test_route(
    data: TestRouteIn, developer: CurrentDeveloper, session: SessionDep, settings: SettingsDep
) -> TestRouteOut:
    """Nothing is sent: it runs the Gateway's matching and Service resolution on your rules.

    Always `200`; `outcome` is `mock`, `proxy` or `error` (with the Gateway's `errorCode`).
    """
    return await test_route.test_route(session, settings, developer, data)
