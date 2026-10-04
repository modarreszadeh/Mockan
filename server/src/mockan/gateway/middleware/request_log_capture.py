"""Request-log capture (arch §6.2 step 2): a no-op passthrough in Phase 1, real in B8a (D-18)."""

from starlette.types import ASGIApp, Receive, Scope, Send


class RequestLogCaptureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
