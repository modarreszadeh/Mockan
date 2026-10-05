"""Gateway CORS for every response, mocked or proxied (D-13, PR-03, PR-09).

Preflights are answered here with 204 and never forwarded. The Developer comes straight from the
first path segment so error responses stay readable by the browser; an unknown slug falls back to
the default origins.
"""

from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mockan.domain.validation import origin_is_allowed
from mockan.gateway.context import is_internal, snapshot_for, split_slug
from mockan.gateway.problems import SOURCE_HEADER
from mockan.matching.snapshot import RuleSnapshotProvider

_EXPOSED = "X-Mockan-Source, X-Mockan-Rule-Id"
_MAX_AGE = "600"


class MockanCorsMiddleware:
    def __init__(
        self, app: ASGIApp, *, provider: RuleSnapshotProvider, default_origins: Sequence[str]
    ) -> None:
        self.app = app
        self._provider = provider
        self._default_origins = tuple(default_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_internal(scope):
            await self.app(scope, receive, send)
            return

        snapshot = snapshot_for(scope, self._provider)
        slug, _ = split_slug(scope["path"])
        developer = snapshot.developer_for_slug(slug) if slug else None
        origins = developer.allowed_origins if developer is not None else self._default_origins

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        allowed = origin is not None and origin_is_allowed(origin, origins)

        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            response = _preflight(headers, origin if allowed else None)
            await response(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": _with_cors(message["headers"], origin, allowed)}
            await send(message)

        await self.app(scope, receive, send_with_cors)


def _preflight(request_headers: Headers, allowed_origin: str | None) -> Response:
    # OQ-B2: a Mockan-answered preflight reports `mock`.
    headers = {
        SOURCE_HEADER: "mock",
        "vary": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
    }
    if allowed_origin is not None:
        headers["access-control-allow-origin"] = allowed_origin
        headers["access-control-allow-credentials"] = "true"
        headers["access-control-allow-methods"] = request_headers["access-control-request-method"]
        requested = request_headers.get("access-control-request-headers")
        if requested:
            headers["access-control-allow-headers"] = requested
        headers["access-control-max-age"] = _MAX_AGE
    return Response(status_code=204, headers=headers)


def _with_cors(
    raw_headers: list[tuple[bytes, bytes]], origin: str | None, allowed: bool
) -> list[tuple[bytes, bytes]]:
    # Upstream and mock `Access-Control-*` headers are replaced by Mockan's (PR-03).
    kept = [(n, v) for n, v in raw_headers if not n.lower().startswith(b"access-control-")]
    vary = [v.decode("latin-1") for n, v in kept if n.lower() == b"vary"]
    kept = [(n, v) for n, v in kept if n.lower() != b"vary"]
    tokens = [t.strip() for value in vary for t in value.split(",") if t.strip()]
    if "*" not in tokens and "origin" not in (t.lower() for t in tokens):
        tokens.append("Origin")
    kept.append((b"vary", ", ".join(tokens).encode("latin-1")))
    if allowed and origin is not None:
        kept += [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-credentials", b"true"),
            (b"access-control-expose-headers", _EXPOSED.encode("latin-1")),
        ]
    return kept
