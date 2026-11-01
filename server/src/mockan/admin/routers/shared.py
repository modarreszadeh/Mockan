"""`/shared/*`: public, read-only views reached by a share link. No sign-in (S-3)."""

from fastapi import APIRouter, Response

from mockan.admin.deps import SessionDep, SettingsDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.shared import SharedRuleOut
from mockan.admin.services import shared

router = APIRouter(prefix="/shared", tags=["shared"])

# The page is the live state of a private rule: never cached, never indexed.
_HEADERS = {"cache-control": "no-store", "x-robots-tag": "noindex"}


@router.get("/rules/{token}", response_model=SharedRuleOut, responses=problems(404))
async def get_shared_rule(
    token: str, response: Response, session: SessionDep, settings: SettingsDep
) -> SharedRuleOut:
    """Unknown, revoked and disabled-owner links are all `404 not_found`."""
    response.headers.update(_HEADERS)
    return await shared.get_shared_rule(session, token, settings.public_base_url)
