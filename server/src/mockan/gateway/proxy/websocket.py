"""WebSocket bridge: accept the browser's socket, connect to the upstream, pump both ways (D-15).

The upstream is connected *first*, so its chosen subprotocol can be offered to the browser and a
failed handshake (401, 404, unreachable...) is answered as a real HTTP response instead of an
accepted-then-closed socket. Close codes travel in both directions.
"""

import asyncio

import structlog
from starlette.responses import Response
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from mockan.domain.errors import ErrorCode
from mockan.gateway.context import (
    MockanContext,
    developer_not_found_detail,
    find_developer,
    set_context,
    snapshot_for,
)
from mockan.gateway.problems import problem_response
from mockan.gateway.proxy.forwarder import ProxyError, ProxyForwarder
from mockan.gateway.proxy.transform import build_response_headers
from mockan.infrastructure.logging import bind_log_context
from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

MAX_MESSAGE_BYTES = 16 * 1024 * 1024  # Uvicorn's own default limit for the browser side
NORMAL_CLOSURE, GOING_AWAY, INTERNAL_ERROR = 1000, 1001, 1011
_SENDABLE_CODES = frozenset(range(1000, 1004)) | frozenset(range(1007, 1015))


def _sendable(code: int | None, fallback: int) -> int:
    """A close code that may appear on the wire (RFC 6455 §7.4); else `fallback`."""
    if code is not None and (code in _SENDABLE_CODES or 3000 <= code <= 4999):
        return code
    return fallback


async def proxy_websocket(websocket: WebSocket) -> None:
    """The catch-all WebSocket route (HTTP middleware does not run for WebSockets)."""
    app = websocket.app
    forwarder: ProxyForwarder | None = app.state.forwarder
    settings: MockanSettings = app.state.settings
    if forwarder is None:
        raise RuntimeError("The WebSocket route ran without a started forwarder.")
    scope = websocket.scope
    path: str = scope["path"]

    snapshot = snapshot_for(scope, app.state.snapshot_provider)
    developer, slug, rest = find_developer(snapshot, path)
    if developer is None:
        await _refuse(
            websocket,
            problem_response(
                ErrorCode.DEVELOPER_NOT_FOUND,
                404,
                developer_not_found_detail(slug),
                public_base_url=settings.public_base_url,
                developer=slug,
                path=path,
            ),
        )
        return
    context = MockanContext(snapshot=snapshot, developer=developer, path_after_slug=rest)
    set_context(scope, context)
    bind_log_context(developer=developer.slug)

    def problem(code: ErrorCode, status: int, detail: str) -> Response:
        return problem_response(
            code,
            status,
            detail,
            public_base_url=settings.public_base_url,
            developer=developer.slug,
            path=path,
        )

    try:
        plan = forwarder.plan(scope, context, websocket=True)
    except ProxyError as error:
        await _refuse(websocket, problem(error.code, error.status, error.detail))
        return

    # The ws(s) URI of the destination; the Origin goes through `origin=` (not a plain header).
    uri = ("wss" if plan.url.scheme == "https" else "ws") + str(plan.url)[len(plan.url.scheme) :]
    origin = next((value for name, value in plan.headers if name == "origin"), None)
    headers = [(name, value) for name, value in plan.headers if name not in ("origin", "host")]
    try:
        upstream = await connect(
            uri,
            origin=origin,  # type: ignore[arg-type]  # websockets types it as a NewType
            subprotocols=scope.get("subprotocols") or None,
            additional_headers=headers,
            user_agent_header=None,  # the browser's User-Agent travels in `headers`
            proxy=None,  # never via environment proxies (see create_http_client)
            open_timeout=plan.timeout_seconds,
            max_size=MAX_MESSAGE_BYTES,
        )
    except InvalidStatus as error:  # the upstream refused the upgrade: pass its answer on
        response = error.response
        refusal = Response(
            content=bytes(response.body or b""),
            status_code=response.status_code,
            headers=dict(build_response_headers(list(response.headers.raw_items()), plan.mapping)),
        )
        await _refuse(websocket, refusal)
        return
    except TimeoutError:
        log.warning("upstream_timeout", service=plan.service_name, websocket=True)
        await _refuse(
            websocket,
            problem(
                ErrorCode.UPSTREAM_TIMEOUT,
                504,
                f"The upstream did not accept the WebSocket within {plan.timeout_seconds} s.",
            ),
        )
        return
    except (OSError, InvalidHandshake, ValueError) as error:
        log.warning("upstream_unreachable", service=plan.service_name, error=repr(error))
        await _refuse(
            websocket,
            problem(
                ErrorCode.UPSTREAM_UNREACHABLE,
                502,
                f"Could not open a WebSocket to the upstream of Service '{plan.service_name}'.",
            ),
        )
        return

    async with upstream:
        await websocket.accept(subprotocol=upstream.subprotocol)
        await _pump(websocket, upstream)


async def _refuse(websocket: WebSocket, response: Response) -> None:
    """Reject the handshake with an HTTP response when the server supports it, else close."""
    if "websocket.http.response" in websocket.scope.get("extensions", {}):
        await websocket.send_denial_response(response)
    else:  # the ASGI server can't send a body: it turns this into a plain 403
        await websocket.close(code=INTERNAL_ERROR)


async def _pump(websocket: WebSocket, upstream: ClientConnection) -> None:
    """Copy frames both ways until either side closes, then close the other with the same code."""

    async def to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                code = _sendable(message.get("code"), NORMAL_CLOSURE)
                await upstream.close(code=code, reason=message.get("reason") or "")
                return
            if message.get("text") is not None:
                await upstream.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream.send(message["bytes"])

    async def to_client() -> None:
        try:
            async for frame in upstream:
                if isinstance(frame, str):
                    await websocket.send_text(frame)
                else:
                    await websocket.send_bytes(frame)
        except ConnectionClosed:
            pass  # the upstream dropped the connection; `close_code` says how
        # 1005 (no status) is a normal end; 1006 (lost) means the upstream failed.
        lost = upstream.close_code == 1006
        code = _sendable(upstream.close_code, INTERNAL_ERROR if lost else NORMAL_CLOSURE)
        await websocket.close(code=code, reason=upstream.close_reason or None)

    pumps = (asyncio.create_task(to_upstream()), asyncio.create_task(to_client()))
    try:
        await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for pump in pumps:
            pump.cancel()
        results = await asyncio.gather(*pumps, return_exceptions=True)
    for result in results:
        # A peer that vanished mid-send is an ordinary end of the session; anything else is a bug.
        if isinstance(result, BaseException) and not isinstance(
            result, asyncio.CancelledError | ConnectionClosed | WebSocketDisconnect | RuntimeError
        ):
            log.error("websocket_bridge_failed", error=repr(result))
