"""Request-log capture (arch §6.2 step 2, PR-12, D-18).

Wraps `receive` and `send` to tee at most 16 KB of each body without buffering anything else (arch
§14 rule 3), and when the response ends offers one `LogEntry` to a bounded queue with `put_nowait`
(a full queue drops the entry and counts it). Only requests that reached a Developer are logged:
an unknown slug has nobody to show the entry to, and a preflight is answered before resolution.
"""

import time
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mockan.domain.constants import SAMPLE_BYTES
from mockan.domain.enums import RequestSource
from mockan.gateway.context import get_context, is_internal
from mockan.infrastructure.request_log import LogEntry, RequestLogQueue

_SOURCES = {
    b"mock": RequestSource.MOCKED,
    b"proxy": RequestSource.PROXIED,
    b"error": RequestSource.ERROR,
}


def _tee(sample: bytearray, message: Message) -> None:
    room = SAMPLE_BYTES - len(sample)
    if room > 0:
        sample.extend(message.get("body", b"")[:room])


class RequestLogCaptureMiddleware:
    def __init__(self, app: ASGIApp, *, queue: RequestLogQueue | None = None) -> None:
        self.app = app
        self._queue = queue

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._queue is None or scope["type"] != "http" or is_internal(scope):
            await self.app(scope, receive, send)
            return

        started_at = datetime.now(UTC)
        clock = time.perf_counter()
        scope.setdefault("state", {})  # the inner steps put their context in this same dict
        request_sample, response_sample = bytearray(), bytearray()
        status = 0
        response_headers: list[tuple[bytes, bytes]] = []

        async def tee_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                _tee(request_sample, message)
            return message

        async def tee_send(message: Message) -> None:
            nonlocal status, response_headers
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                _tee(response_sample, message)
            await send(message)

        try:
            await self.app(scope, tee_receive, tee_send)
        finally:
            context = get_context(scope)
            if context is not None and status:
                self._queue.offer(
                    LogEntry(
                        developer_id=context.developer.id,
                        timestamp=started_at,
                        method=scope["method"],
                        path=context.path_after_slug,
                        query=scope.get("query_string", b"").decode("latin-1"),
                        service_id=context.service_id,
                        source=_source(response_headers),
                        rule_id=context.rule_id,
                        status_code=status,
                        duration_ms=int((time.perf_counter() - clock) * 1000),
                        request_headers=scope["headers"],
                        response_headers=response_headers,
                        request_sample=bytes(request_sample),
                        response_sample=bytes(response_sample),
                    )
                )


def _source(headers: list[tuple[bytes, bytes]]) -> RequestSource:
    for name, value in headers:
        if name.lower() == b"x-mockan-source":
            return _SOURCES.get(value.lower(), RequestSource.ERROR)
    return RequestSource.ERROR
