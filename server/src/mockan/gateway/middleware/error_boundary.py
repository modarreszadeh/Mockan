"""Turns an unexpected exception into an `internal_error` problem that still gets CORS headers."""

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mockan.domain.errors import ErrorCode
from mockan.gateway.context import get_context, is_internal
from mockan.gateway.problems import problem_response

log = structlog.get_logger()


class ErrorBoundaryMiddleware:
    def __init__(self, app: ASGIApp, *, public_base_url: str) -> None:
        self.app = app
        self._public_base_url = public_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_internal(scope):
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:  # outermost handler of the data plane: log, answer, never leak a trace
            log.error("unhandled_error", path=scope["path"], exc_info=True)
            if started:
                raise  # too late to change the response; let the server drop the connection
            context = get_context(scope)
            response = problem_response(
                ErrorCode.INTERNAL_ERROR,
                500,
                "The Gateway failed to process the request.",
                public_base_url=self._public_base_url,
                developer=context.developer.slug if context else None,
                path=scope["path"],
            )
            await response(scope, receive, send)
