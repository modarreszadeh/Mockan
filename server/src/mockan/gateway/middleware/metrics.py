"""Request metrics (PR-17): `mockan_requests_total{source}` and `mockan_proxy_duration_ms`.

Outermost, so it sees every HTTP response the Gateway sends (unknown slugs and preflights too).
The source comes from the response's `X-Mockan-Source`, which every response carries (rule 7).
Health checks and WebSockets are not counted. Recording is a couple of in-memory operations.
"""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mockan.gateway.context import is_internal
from mockan.infrastructure.telemetry import Telemetry


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, *, telemetry: Telemetry) -> None:
        self.app = app
        self._telemetry = telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_internal(scope):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        source = b"error"

        async def counting_send(message: Message) -> None:
            nonlocal source
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    if name.lower() == b"x-mockan-source":
                        source = value.lower()
                        break
            await send(message)

        try:
            await self.app(scope, receive, counting_send)
        finally:
            label = source.decode("latin-1")
            self._telemetry.requests.add(1, {"source": label})
            if label == "proxy":
                self._telemetry.proxy_duration.record((time.perf_counter() - started) * 1000)
