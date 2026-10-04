"""Gateway FastAPI app factory: lifespan, pipeline order (arch §6.2) and health routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.responses import Response

from mockan.domain.enums import RequestSource
from mockan.domain.errors import ErrorCode
from mockan.gateway import health
from mockan.gateway.context import get_context
from mockan.gateway.middleware.cors import MockanCorsMiddleware
from mockan.gateway.middleware.developer_resolution import DeveloperResolutionMiddleware
from mockan.gateway.middleware.error_boundary import ErrorBoundaryMiddleware
from mockan.gateway.middleware.mock_matching import MockMatchingMiddleware
from mockan.gateway.middleware.request_log_capture import RequestLogCaptureMiddleware
from mockan.gateway.problems import problem_response
from mockan.gateway.snapshot_service import SnapshotService
from mockan.infrastructure.db.session import create_engine, create_session_factory
from mockan.infrastructure.logging import configure_logging
from mockan.infrastructure.settings import MockanSettings
from mockan.matching.errors import ServiceNotResolvedError
from mockan.matching.service_resolver import resolve_service
from mockan.matching.snapshot import RuleSnapshotProvider

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


async def _proxy_placeholder(request: Request) -> Response:
    """Resolve the Service; the real forwarder replaces the 501 in B4."""
    context = get_context(request.scope)
    settings: MockanSettings = request.app.state.settings
    if context is None:  # unreachable: DeveloperResolutionMiddleware always sets it
        return problem_response(
            ErrorCode.INTERNAL_ERROR,
            500,
            "No request context.",
            public_base_url=settings.public_base_url,
            path=request.url.path,
        )
    context.source = RequestSource.ERROR
    try:
        resolve_service(context.snapshot, context.developer, context.path_after_slug)
    except ServiceNotResolvedError as error:
        return problem_response(
            ErrorCode.SERVICE_NOT_RESOLVED,
            502,
            error.detail,
            public_base_url=settings.public_base_url,
            developer=context.developer.slug,
            path=request.url.path,
        )
    # TODO(B4): replace with ProxyForwarder (httpx streaming + WebSocket bridge).
    return problem_response(
        ErrorCode.INTERNAL_ERROR,
        501,
        "Proxying is not implemented yet.",
        public_base_url=settings.public_base_url,
        developer=context.developer.slug,
        path=request.url.path,
    )


def create_app(
    settings: MockanSettings | None = None,
    snapshot_provider: RuleSnapshotProvider | None = None,
) -> FastAPI:
    """Build the Gateway.

    Passing a `snapshot_provider` (tests) skips the database entirely: no `SnapshotService` runs.
    """
    settings = settings or MockanSettings()
    provider = snapshot_provider or RuleSnapshotProvider()
    manages_snapshot = snapshot_provider is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Background tasks start and stop here, never at import time (conventions §3).
        configure_logging(settings.log_level, settings.log_format)
        engine = service = None
        if manages_snapshot:
            engine = create_engine(settings)
            service = SnapshotService(settings, provider, create_session_factory(engine))
            app.state.snapshot_service = service
            await service.start()
        try:
            yield
        finally:
            if service is not None:
                await service.stop()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Mockan Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.snapshot_provider = provider
    app.state.snapshot_service = None

    app.include_router(health.router)
    app.add_route("/{path:path}", _proxy_placeholder, methods=_METHODS)

    # `add_middleware` makes the last one added the outermost. Order, outermost first (arch §6.2):
    # request log, CORS, error boundary, Developer resolution, mock matching, then the proxy route.
    app.add_middleware(MockMatchingMiddleware)
    app.add_middleware(
        DeveloperResolutionMiddleware, provider=provider, public_base_url=settings.public_base_url
    )
    app.add_middleware(ErrorBoundaryMiddleware, public_base_url=settings.public_base_url)
    app.add_middleware(
        MockanCorsMiddleware, provider=provider, default_origins=settings.default_allowed_origins
    )
    app.add_middleware(RequestLogCaptureMiddleware)
    return app
