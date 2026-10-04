"""Sign-in and the auth dependencies: `current_developer`, `writable_developer`, `require_admin`.

The Panel uses a signed session cookie (`/auth/login` → IdP → `/auth/callback`); API clients send
a bearer JWT (D-12). `MOCKAN_AUTH_MODE=dev` replaces the IdP with `/auth/login?as=<name>` (G-9).
"""

import uuid
from collections.abc import Mapping
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response

from mockan.admin.deps import SessionDep, SettingsDep
from mockan.admin.oidc import OidcClient, TokenError
from mockan.admin.problems import DomainError
from mockan.admin.schemas.problem import problems
from mockan.admin.services import developers
from mockan.domain.errors import ErrorCode
from mockan.infrastructure.db.models import Developer
from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

SESSION_KEY = "developer_id"
_DEV_NAME = r"^[A-Za-z0-9._-]{1,50}$"
_MAX_DISPLAY_NAME = 100

router = APIRouter(prefix="/auth", tags=["auth"])


def _unauthenticated(detail: str | None = None) -> DomainError:
    return DomainError(ErrorCode.UNAUTHENTICATED, 401, "Sign in to continue", detail)


def panel_url(settings: MockanSettings) -> str:
    return settings.panel_base_path.rstrip("/") + "/"


def display_name_from_claims(claims: Mapping[str, Any]) -> str:
    """`name` → `preferred_username` → `email` (G-9 / plan B5); the first non-empty one."""
    for claim in ("name", "preferred_username", "email"):
        value = claims.get(claim)
        if isinstance(value, str) and value.strip():
            return value.strip()[:_MAX_DISPLAY_NAME]
    return "Developer"


# ---- dependencies ----


async def current_developer(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Developer:
    """The signed-in Developer (cookie, else bearer token); `401 unauthenticated` otherwise.

    A disabled Developer is still returned so `GET /me` can say so; writes go through
    `writable_developer`.
    """
    stored = request.session.get(SESSION_KEY)
    if stored:
        try:
            developer = await developers.get_by_id(session, uuid.UUID(str(stored)))
        except ValueError:
            developer = None
        if developer is not None:
            return developer
        request.session.clear()  # the Developer is gone: drop the stale cookie

    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        oidc: OidcClient | None = request.app.state.oidc
        if oidc is None:
            raise _unauthenticated("Bearer tokens need MOCKAN_AUTH_MODE=oidc.")
        try:
            claims = await oidc.verify_bearer(token.strip())
        except TokenError as error:
            raise _unauthenticated(str(error)) from error
        return await developers.sign_in(
            session,
            settings,
            subject=str(claims["sub"]),
            display_name=display_name_from_claims(claims),
        )
    raise _unauthenticated()


async def writable_developer(
    developer: Annotated[Developer, Depends(current_developer)],
) -> Developer:
    if not developer.is_enabled:
        raise DomainError(
            ErrorCode.DEVELOPER_DISABLED,
            403,
            "Your workspace is disabled",
            "Ask a Mockan admin to enable it.",
        )
    return developer


async def require_admin(
    developer: Annotated[Developer, Depends(writable_developer)],
) -> Developer:
    if not developer.is_admin:
        raise DomainError(
            ErrorCode.FORBIDDEN, 403, "Only Mockan admins can change the Service catalog"
        )
    return developer


CurrentDeveloper = Annotated[Developer, Depends(current_developer)]
WritableDeveloper = Annotated[Developer, Depends(writable_developer)]
AdminDeveloper = Annotated[Developer, Depends(require_admin)]


# ---- routes ----


def _start_session(request: Request, developer: Developer) -> None:
    request.session.clear()  # drops the OIDC state/nonce, and any previous Developer
    request.session[SESSION_KEY] = str(developer.id)


@router.get(
    "/login",
    status_code=303,
    response_class=RedirectResponse,
    responses={**problems(422), 303: {"description": "Redirect to the IdP (or the Panel)."}},
    summary="Start sign-in",
)
async def login(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    as_: Annotated[
        str | None,
        Query(alias="as", pattern=_DEV_NAME, description="Dev mode only: who to sign in as."),
    ] = None,
    admin: Annotated[bool, Query(description="Dev mode only: sign in as an admin.")] = False,
) -> Response:
    """OIDC: redirect to the identity provider. Dev mode (G-9): sign in as `dev:<as>` directly."""
    if settings.auth_mode == "dev":
        name = as_ or "dev"
        developer = await developers.sign_in(
            session, settings, subject=f"dev:{name}", display_name=name, grant_admin=admin
        )
        _start_session(request, developer)
        return RedirectResponse(panel_url(settings), status_code=303)
    oidc: OidcClient = request.app.state.oidc
    return await oidc.authorize_redirect(request, str(request.url_for("auth_callback")))


@router.get(
    "/callback",
    name="auth_callback",
    status_code=303,
    response_class=RedirectResponse,
    responses=problems(401),
    summary="OIDC redirect target",
)
async def callback(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    if settings.auth_mode == "dev":
        raise DomainError(ErrorCode.NOT_FOUND, 404, "Not found")
    oidc: OidcClient = request.app.state.oidc
    try:
        claims = await oidc.complete_login(request)
    except TokenError as error:
        log.warning("oidc_login_failed", reason=str(error))
        raise _unauthenticated(str(error)) from error
    developer = await developers.sign_in(
        session,
        settings,
        subject=str(claims["sub"]),
        display_name=display_name_from_claims(claims),
    )
    _start_session(request, developer)
    return RedirectResponse(panel_url(settings), status_code=303)


@router.post("/logout", status_code=204, summary="Sign out")
async def logout(request: Request) -> Response:
    # TODO(OQ-04): no RP-initiated logout at the IdP yet, so SSO may sign the user straight back in.
    request.session.clear()
    return Response(status_code=204)
