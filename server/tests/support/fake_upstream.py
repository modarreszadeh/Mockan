"""A small real upstream for proxy tests: echo, streaming, SSE, WebSocket, redirects, cookies...

Served by a real Uvicorn (`LiveServer`), never mocked, so streaming and header handling are real.
"""

import asyncio
import base64
import gzip
import hashlib
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
CHUNK = b"0123456789abcdef" * 4096  # 64 KiB, the unit of /download
SMALL_BODY_BYTES = 64 * 1024


def download_sha256(megabytes: int) -> str:
    digest = hashlib.sha256()
    for _ in range(megabytes * 16):
        digest.update(CHUNK)
    return digest.hexdigest()


@dataclass
class UpstreamState:
    """What the upstream observed, for assertions made from the test thread."""

    sse_closed: threading.Event = field(default_factory=threading.Event)
    ws_close_codes: list[int] = field(default_factory=list)
    ws_closed: threading.Event = field(default_factory=threading.Event)

    def reset(self) -> None:
        self.sse_closed.clear()
        self.ws_close_codes.clear()
        self.ws_closed.clear()


def build_fake_upstream(state: UpstreamState) -> Starlette:
    async def echo(request: Request) -> Response:
        digest, size, kept = hashlib.sha256(), 0, bytearray()
        async for chunk in request.stream():
            digest.update(chunk)
            size += len(chunk)
            if len(kept) <= SMALL_BODY_BYTES:
                kept.extend(chunk)
        return JSONResponse(
            {
                "method": request.method,
                "rawPath": request.scope["raw_path"].decode("latin-1"),
                "path": request.url.path,
                "query": request.scope["query_string"].decode("latin-1"),
                "headers": [
                    [k.decode("latin-1"), v.decode("latin-1")] for k, v in request.scope["headers"]
                ],
                "bodyLength": size,
                "bodySha256": digest.hexdigest(),
                "body": base64.b64encode(bytes(kept)).decode()
                if size <= SMALL_BODY_BYTES
                else None,
            }
        )

    async def stream(request: Request) -> Response:
        async def chunks() -> AsyncIterator[bytes]:
            for index in range(5):
                yield f"chunk-{index}|".encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(chunks(), media_type="text/plain")

    async def sse(request: Request) -> Response:
        count = int(request.query_params.get("count", "5"))
        interval = float(request.query_params.get("interval", "0.3"))

        async def events() -> AsyncIterator[str]:
            try:
                for index in range(count):
                    yield f"data: {index}\n\n"
                    await asyncio.sleep(interval)
            finally:  # runs when the client (the Gateway) goes away mid-stream
                state.sse_closed.set()

        return StreamingResponse(events(), media_type="text/event-stream")

    async def download(request: Request) -> Response:
        megabytes = int(request.query_params.get("mb", "10"))

        async def chunks() -> AsyncIterator[bytes]:
            for _ in range(megabytes * 16):
                yield CHUNK

        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={"content-length": str(megabytes * 16 * len(CHUNK))},
        )

    async def truncated(request: Request) -> Response:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"partial"
            raise RuntimeError("the upstream died mid-body")  # Uvicorn drops the connection

        return StreamingResponse(chunks(), headers={"content-length": "1000"})

    async def slow(request: Request) -> Response:
        await asyncio.sleep(float(request.query_params.get("seconds", "2")))
        return Response("late", media_type="text/plain")

    async def redirect(request: Request) -> Response:
        host = request.headers["host"]
        return Response(status_code=302, headers={"location": f"http://{host}/echo?via=redirect"})

    async def redirect_root(request: Request) -> Response:
        return Response(status_code=301, headers={"location": "/echo?via=root-relative"})

    async def created(request: Request) -> Response:
        host = request.headers["host"]
        return JSONResponse({"id": 1}, status_code=201, headers={"location": f"http://{host}/echo"})

    async def set_cookie(request: Request) -> Response:
        response = Response("cookies", media_type="text/plain")
        response.headers.append("set-cookie", "a=1; Domain=127.0.0.1; Path=/x; HttpOnly; Secure")
        response.headers.append("set-cookie", "b=2")
        response.headers.append("set-cookie", "c=3; Path=/; SameSite=None; Secure")
        return response

    async def cors(request: Request) -> Response:
        return Response(
            "cors",
            media_type="text/plain",
            headers={
                "access-control-allow-origin": "https://evil.example",
                "access-control-allow-credentials": "true",
                "access-control-expose-headers": "x-secret",
                "x-keep": "yes",
            },
        )

    async def response_headers(request: Request) -> Response:
        response = Response("headers", media_type="text/plain")
        for name, value in (
            ("connection", "x-private"),
            ("x-private", "secret"),
            ("keep-alive", "timeout=5"),
            ("proxy-authenticate", "Basic"),
            ("server", "fake-upstream"),
            ("x-mockan-source", "mock"),
            ("x-keep", "yes"),
        ):
            response.headers.append(name, value)
        return response

    async def gzipped(request: Request) -> Response:
        return Response(
            gzip.compress(b"hello gateway " * 50),
            media_type="text/plain",
            headers={"content-encoding": "gzip"},
        )

    async def status(request: Request) -> Response:
        code = int(request.path_params["code"])
        return Response(status_code=code, headers={"x-keep": "yes"})

    async def ws_echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await _echo(websocket, state)

    async def ws_headers(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(
            json.dumps(
                {
                    "headers": [
                        [k.decode("latin-1"), v.decode("latin-1")]
                        for k, v in websocket.scope["headers"]
                    ],
                    "path": websocket.url.path,
                    "query": websocket.scope["query_string"].decode("latin-1"),
                    "subprotocols": websocket.scope.get("subprotocols", []),
                }
            )
        )
        await _echo(websocket, state)

    async def ws_proto(websocket: WebSocket) -> None:
        offered = websocket.scope.get("subprotocols", [])
        await websocket.accept(subprotocol="chat" if "chat" in offered else None)
        await _echo(websocket, state)

    async def ws_deny(websocket: WebSocket) -> None:
        await websocket.send_denial_response(
            JSONResponse({"error": "unauthorized"}, status_code=401)
        )

    return Starlette(
        routes=[
            Route("/echo", echo, methods=ALL_METHODS),
            Route("/echo/{rest:path}", echo, methods=ALL_METHODS),
            Route("/stream", stream),
            Route("/sse", sse),
            Route("/download", download),
            Route("/truncated", truncated),
            Route("/slow", slow),
            Route("/redirect", redirect),
            Route("/redirect-root", redirect_root),
            Route("/created", created, methods=["POST"]),
            Route("/set-cookie", set_cookie),
            Route("/cors", cors),
            Route("/response-headers", response_headers),
            Route("/gzip", gzipped),
            Route("/status/{code:int}", status, methods=ALL_METHODS),
            WebSocketRoute("/ws", ws_echo),
            WebSocketRoute("/ws/headers", ws_headers),
            WebSocketRoute("/ws/proto", ws_proto),
            WebSocketRoute("/ws/deny", ws_deny),
        ]
    )


async def _echo(websocket: WebSocket, state: UpstreamState) -> None:
    """Echo frames; `close:<code>:<reason>` makes the upstream close with that code."""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                state.ws_close_codes.append(message.get("code", 1005))
                return
            if message.get("bytes") is not None:
                await websocket.send_bytes(message["bytes"])
                continue
            text: str = message["text"]
            if text.startswith("close:"):
                _, code, reason = text.split(":", 2)
                await websocket.close(code=int(code), reason=reason)
                return
            await websocket.send_text(text)
    except WebSocketDisconnect as error:
        state.ws_close_codes.append(error.code)
    finally:
        state.ws_closed.set()
