"""ProxyForwarder: plans the upstream request and streams it both ways (D-15, PR-02, PR-04, NFR-04).

One `httpx.AsyncClient` per process (created in the app lifespan) streams the request body from the
ASGI `receive` and the response body back as raw bytes, so nothing is ever buffered in full
(arch §14 rule 3). The destination is re-checked against the allowlist right before sending
(arch §14 rule 4). The WebSocket bridge lives in `websocket.py` and shares `ProxyForwarder.plan`.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import anyio
import httpx
import structlog
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from mockan.domain.enums import RequestSource
from mockan.domain.errors import ErrorCode
from mockan.domain.validation import host_is_allowed
from mockan.gateway.context import MockanContext, get_context
from mockan.gateway.problems import problem_response
from mockan.gateway.proxy.transform import (
    ForwardInfo,
    HeaderList,
    RouteMapping,
    build_request_headers,
    build_response_headers,
    origin_of,
)
from mockan.infrastructure.logging import bind_log_context
from mockan.infrastructure.settings import MockanSettings
from mockan.matching.errors import ServiceNotResolvedError
from mockan.matching.service_resolver import resolve_service
from mockan.matching.upstream import build_upstream_path, build_upstream_url

log = structlog.get_logger()

# Connection pool sizing for the one shared client (NFR-01: reuse upstream connections).
MAX_CONNECTIONS = 512
MAX_KEEPALIVE_CONNECTIONS = 128
CLIENT_DISCONNECTED = 499  # nginx's convention; nobody reads this response


def create_http_client() -> httpx.AsyncClient:
    """The shared upstream client. Redirects are the browser's business, never followed (D-15).

    `trust_env=False`: the Gateway must reach upstreams directly, whatever proxy variables the host
    happens to export.
    """
    return httpx.AsyncClient(
        follow_redirects=False,
        http2=False,
        trust_env=False,
        timeout=None,  # per request, from ServiceEnvironment.timeout_seconds
        limits=httpx.Limits(
            max_connections=MAX_CONNECTIONS, max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS
        ),
    )


class ProxyError(Exception):
    """A request that can't be forwarded; becomes a problem+json (or a refused WebSocket)."""

    def __init__(self, code: ErrorCode, status: int, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.status = status
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ProxyPlan:
    url: httpx.URL  # http(s) destination, already allowlisted
    headers: HeaderList  # request headers to send, transformed (§6.3)
    mapping: RouteMapping  # upstream URL space -> Mockan URL space (Location, Set-Cookie)
    timeout_seconds: int
    service_name: str


def _decode(headers: Sequence[tuple[bytes, bytes]]) -> HeaderList:
    return [(name.decode("latin-1"), value.decode("latin-1")) for name, value in headers]


def _encode(headers: HeaderList) -> list[tuple[bytes, bytes]]:
    return [
        (name.encode("latin-1"), value.encode("latin-1", errors="replace"))
        for name, value in headers
    ]


def _allowlist_host(url: httpx.URL) -> str:
    return f"[{url.host}]" if ":" in url.host else url.host


class ProxyForwarder:
    def __init__(self, client: httpx.AsyncClient, settings: MockanSettings) -> None:
        self._client = client
        self._settings = settings

    def plan(self, scope: Scope, context: MockanContext, *, websocket: bool = False) -> ProxyPlan:
        """Resolve the Service and build the upstream request (path, query, headers).

        Raises `ProxyError` for an unresolved Service, a malformed destination or a host outside
        `MOCKAN_ALLOWED_UPSTREAM_HOSTS`. Pure apart from reading settings: no network.
        """
        try:
            resolved = resolve_service(context.snapshot, context.developer, context.path_after_slug)
        except ServiceNotResolvedError as error:
            raise ProxyError(ErrorCode.SERVICE_NOT_RESOLVED, 502, error.detail) from error
        service, environment = resolved.service, resolved.environment
        bind_log_context(service=service.name)
        context.service_id = service.id  # for the request log

        raw_path = scope.get("raw_path")
        path = build_upstream_path(
            raw_path=raw_path.decode("latin-1") if raw_path else None,
            upstream_path=resolved.upstream_path,
            service_prefix=service.path_prefix,
            strip_prefix=service.strip_prefix,
        )
        raw_query = scope.get("query_string", b"").decode("latin-1")
        try:
            url = httpx.URL(build_upstream_url(environment.base_url, path, raw_query))
        except httpx.InvalidURL as error:
            raise ProxyError(
                ErrorCode.UPSTREAM_UNREACHABLE,
                502,
                f"The base URL of Service '{service.name}' is not a valid URL.",
            ) from error

        host = _allowlist_host(url)
        if url.scheme not in ("http", "https") or not host_is_allowed(
            host, self._settings.allowed_upstream_hosts
        ):
            # Defence in depth (arch §14 rule 4, NFR-06): the Admin checked this when saving.
            log.error(
                "upstream_host_not_allowed",
                host=host,
                scheme=url.scheme,
                developer=context.developer.slug,
                service=service.name,
            )
            raise ProxyError(
                ErrorCode.UPSTREAM_UNREACHABLE,
                502,
                f"Destination host '{host}' is not allowed by MOCKAN_ALLOWED_UPSTREAM_HOSTS.",
            )

        upstream_origin = origin_of(environment.base_url)
        headers = build_request_headers(
            _decode(scope["headers"]),
            info=ForwardInfo(
                developer_slug=context.developer.slug,
                scheme=_forwarded_scheme(scope),
                host=_header(scope, b"host"),
                client_ip=scope["client"][0] if scope.get("client") else None,
            ),
            upstream_host=url.netloc.decode("ascii"),
            extra_headers=environment.extra_headers,
            rewrite_origin_to=upstream_origin if service.rewrite_origin else None,
            websocket=websocket,
        )
        return ProxyPlan(
            url=url,
            headers=headers,
            mapping=RouteMapping(
                developer_slug=context.developer.slug,
                public_base_url=self._settings.public_base_url,
                upstream_base_url=environment.base_url,
                service_prefix=service.path_prefix,
                strip_prefix=service.strip_prefix,
            ),
            timeout_seconds=environment.timeout_seconds,
            service_name=service.name,
        )

    async def forward(self, request: Request, context: MockanContext) -> Response:
        """Stream `request` to the upstream and the upstream's response back."""
        scope = request.scope
        try:
            plan = self.plan(scope, context)
        except ProxyError as error:
            return self._problem(error, context, request.url.path)

        upstream_request = self._client.build_request(
            request.method,
            plan.url,
            headers=_encode(plan.headers),
            # A body-less request must not turn into a chunked one (httpx adds the framing).
            content=request.stream() if _has_body(scope) else None,
            timeout=httpx.Timeout(plan.timeout_seconds),
        )
        try:
            upstream = await self._client.send(upstream_request, stream=True)
        except ClientDisconnect:  # the browser went away while uploading
            context.source = RequestSource.ERROR
            return Response(status_code=CLIENT_DISCONNECTED)
        except httpx.TimeoutException as error:
            log.warning("upstream_timeout", service=plan.service_name, error=type(error).__name__)
            return self._problem(
                ProxyError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    504,
                    f"The upstream did not answer within {plan.timeout_seconds} s.",
                ),
                context,
                request.url.path,
            )
        except httpx.TransportError as error:
            log.warning("upstream_unreachable", service=plan.service_name, error=repr(error))
            return self._problem(
                ProxyError(
                    ErrorCode.UPSTREAM_UNREACHABLE,
                    502,
                    f"Could not reach the upstream of Service '{plan.service_name}'.",
                ),
                context,
                request.url.path,
            )

        context.source = RequestSource.PROXIED
        bind_log_context(source="proxy")
        headers = build_response_headers(_decode(upstream.headers.raw), plan.mapping)
        return UpstreamResponse(upstream, _encode(headers), plan.service_name)

    def _problem(self, error: ProxyError, context: MockanContext, path: str) -> Response:
        context.source = RequestSource.ERROR
        bind_log_context(source="error")
        return problem_response(
            error.code,
            error.status,
            error.detail,
            public_base_url=self._settings.public_base_url,
            developer=context.developer.slug,
            path=path,
        )


class UpstreamResponse(StreamingResponse):
    """The upstream's response, streamed raw (`aiter_raw`: `Content-Encoding` is preserved).

    Closing the upstream response in `__call__`'s `finally` releases its connection however the
    stream ends: completed, upstream error, or the client disconnecting (D-15, NFR-04).
    """

    def __init__(
        self, upstream: httpx.Response, raw_headers: list[tuple[bytes, bytes]], service: str
    ) -> None:
        super().__init__(_stream(upstream, service), status_code=upstream.status_code)
        self.raw_headers = raw_headers  # keeps repeated headers such as Set-Cookie
        self._upstream = upstream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):  # must finish even when the client cancelled us
                await self._upstream.aclose()


async def _stream(upstream: httpx.Response, service: str) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    except httpx.TransportError as error:
        # Headers are already sent: the connection is dropped so the client sees the failure.
        log.warning("upstream_stream_failed", service=service, error=repr(error))
        raise


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _forwarded_scheme(scope: Scope) -> str:
    return "https" if scope.get("scheme", "http") in ("https", "wss") else "http"


def _has_body(scope: Scope) -> bool:
    """Does the request carry a body? (Content-Length > 0, or chunked framing.)"""
    for name, value in scope["headers"]:
        if name == b"transfer-encoding":
            return True
        if name == b"content-length":
            return value.strip() not in (b"", b"0")
    return False


async def proxy_http(request: Request) -> Response:
    """The catch-all route: everything no MockRule answered goes upstream (arch §6.2 step 6)."""
    context = get_context(request.scope)
    forwarder: ProxyForwarder | None = request.app.state.forwarder
    if context is None or forwarder is None:  # unreachable: resolution runs first, lifespan too
        raise RuntimeError("The proxy route ran without a request context or a started forwarder.")
    return await forwarder.forward(request, context)
