"""Gateway FastAPI app factory: lifespan, pipeline order (arch §6.2) and health routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mockan.gateway import health
from mockan.gateway.middleware.cors import MockanCorsMiddleware
from mockan.gateway.middleware.developer_resolution import DeveloperResolutionMiddleware
from mockan.gateway.middleware.error_boundary import ErrorBoundaryMiddleware
from mockan.gateway.middleware.mock_matching import MockMatchingMiddleware
from mockan.gateway.middleware.request_log_capture import RequestLogCaptureMiddleware
from mockan.gateway.proxy.forwarder import ProxyForwarder, create_http_client, proxy_http
from mockan.gateway.proxy.websocket import proxy_websocket
from mockan.gateway.snapshot_service import SnapshotService
from mockan.infrastructure.db.session import create_engine, create_session_factory
from mockan.infrastructure.logging import configure_logging
from mockan.infrastructure.settings import MockanSettings
from mockan.matching.snapshot import RuleSnapshotProvider

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


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
        # D-15: one shared upstream client per process, closed with the app.
        client = create_http_client()
        app.state.http_client = client
        app.state.forwarder = ProxyForwarder(client, settings)
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
            app.state.forwarder = None
            await client.aclose()

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
    app.state.http_client = None  # set by the lifespan
    app.state.forwarder = None

    app.include_router(health.router)
    # Whatever no MockRule answers is proxied (arch §6.2 step 6); WebSockets bypass the HTTP
    # middleware and are resolved inside `proxy_websocket`.
    app.add_route("/{path:path}", proxy_http, methods=_METHODS)
    app.router.add_websocket_route("/{path:path}", proxy_websocket)

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
