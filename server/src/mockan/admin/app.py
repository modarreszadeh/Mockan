"""Admin API FastAPI app factory: routers under `/api/v1`, session auth, problems, the Panel."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import APIRouter, FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from mockan.admin import auth
from mockan.admin.hub import RequestLogHub
from mockan.admin.oidc import OidcClient
from mockan.admin.openapi import use_problem_422
from mockan.admin.problems import install_problem_handlers
from mockan.admin.routers import (
    hubs,
    me,
    request_logs,
    responses,
    rules,
    rules_io,
    service_settings,
    services,
    test_route,
)
from mockan.admin.spa import mount_panel
from mockan.infrastructure.db.migrate import upgrade_to_head
from mockan.infrastructure.db.session import create_engine, create_session_factory
from mockan.infrastructure.logging import configure_logging
from mockan.infrastructure.settings import MockanSettings
from mockan.infrastructure.telemetry import make_tracer_provider

log = structlog.get_logger()

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "mockan_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600
_MIN_SECRET_LENGTH = 32


def _session_secret(settings: MockanSettings) -> str:
    """The cookie-signing key. Dev mode may run without one (sessions then die with the process)."""
    if len(settings.session_secret) >= _MIN_SECRET_LENGTH:
        return settings.session_secret
    if settings.auth_mode == "dev":
        return secrets.token_urlsafe(48)
    raise RuntimeError(
        f"MOCKAN_SESSION_SECRET must be at least {_MIN_SECRET_LENGTH} characters "
        "(random bytes) unless MOCKAN_AUTH_MODE=dev."
    )


def _check_oidc(settings: MockanSettings) -> None:
    missing = [
        name
        for name, value in (
            ("MOCKAN_OIDC_ISSUER", settings.oidc_issuer),
            ("MOCKAN_OIDC_CLIENT_ID", settings.oidc_client_id),
            ("MOCKAN_OIDC_CLIENT_SECRET", settings.oidc_client_secret),
        )
        if not value
    ]
    if missing:  # TODO(OQ-04): provider specifics undecided
        raise RuntimeError(f"{', '.join(missing)} required when MOCKAN_AUTH_MODE=oidc.")


def create_app(
    settings: MockanSettings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    static_dir: Path | None = None,
    tracer_provider: TracerProvider | None = None,
) -> FastAPI:
    """Build the Admin app.

    Passing a `session_factory` (tests) skips creating the engine in the lifespan.
    """
    settings = settings or MockanSettings()
    secret = _session_secret(settings)
    if settings.auth_mode == "oidc":
        _check_oidc(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_format)
        if settings.auth_mode == "dev":
            log.warning(
                "auth_mode_dev",
                detail="Anyone who can reach the Admin API can sign in as any Developer. "
                "MUST NOT be used in shared environments.",
            )
        engine: AsyncEngine | None = None
        if session_factory is None:
            engine = create_engine(settings)
            app.state.session_factory = create_session_factory(engine)
        if settings.migrate_on_startup:
            log.info("migrating_database")
            await upgrade_to_head(settings.database_url)
        hub = RequestLogHub(settings, app.state.session_factory)
        app.state.hub = hub
        await hub.start()
        try:
            yield
        finally:
            await hub.stop()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Mockan Admin API",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory  # else set by the lifespan
    app.state.hub = None  # the request-log hub, started by the lifespan
    app.state.oidc = OidcClient(settings) if settings.auth_mode == "oidc" else None

    install_problem_handlers(app, settings)
    use_problem_422(app)

    # G-12: HttpOnly + SameSite=Lax (Starlette's defaults plus Secure). Dev mode runs over plain
    # http on localhost, where a Secure cookie would not be sent back by every client.
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=settings.auth_mode != "dev",
    )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(auth.router)
    api.include_router(me.router)
    api.include_router(services.router)
    api.include_router(service_settings.router)
    api.include_router(rules_io.router)  # before `/me/rules/{rule_id}`: `export` isn't an id
    api.include_router(rules.router)
    api.include_router(responses.router)
    api.include_router(request_logs.router)
    api.include_router(test_route.router)
    app.include_router(api)
    app.include_router(hubs.router)  # `/hubs/*`: outside `/api/v1`

    if settings.tracing_enabled and tracer_provider is None:
        tracer_provider = make_tracer_provider("mockan-admin", settings)
    if tracer_provider is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)

    panel_dir = static_dir or STATIC_DIR
    if (panel_dir / "index.html").is_file():
        mount_panel(app, panel_dir, settings.panel_base_path)
    return app
