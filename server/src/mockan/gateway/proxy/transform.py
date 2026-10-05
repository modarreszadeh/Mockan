"""ProxyTransformer: pure functions that rewrite a request going upstream and the response coming
back (arch §6.3, PR-02, PR-03, PR-04, PR-15).

Nothing here does I/O or touches ASGI, so every row of the §6.3 table is unit-tested on plain
header lists. Headers are `(name, value)` pairs of `str` (latin-1 decoded), in the original order,
with duplicates preserved (several `Set-Cookie` lines must stay separate).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from mockan.domain.validation import routing_prefix

type HeaderList = list[tuple[str, str]]

SOURCE_PROXY = "proxy"

# RFC 9110 §7.6.1 plus `Proxy-*` (arch §6.3). Headers named in `Connection` are added per message.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
# The handshake of a WebSocket belongs to one hop: the upstream connection negotiates its own.
_WEBSOCKET_HANDSHAKE = frozenset(
    {
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-extensions",
        "sec-websocket-accept",
        "sec-websocket-protocol",
    }
)
# Set by Mockan itself, so whatever the client or the upstream sent is replaced, never trusted.
_REPLACED_ON_REQUEST = frozenset(
    {"host", "x-forwarded-proto", "x-forwarded-host", "x-forwarded-prefix", "x-mockan-developer"}
)
# `Expect: 100-continue` is answered by the ASGI server; forwarding it would stall the upstream.
_DROPPED_ON_REQUEST = frozenset({"expect"})
# Uvicorn adds its own `Date` and `Server`; an upstream copy would be a duplicate header.
_DROPPED_ON_RESPONSE = frozenset({"date", "server", "x-mockan-source", "x-mockan-rule-id"})

_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _is_proxy_header(name: str) -> bool:
    return name.startswith("proxy-")


def hop_by_hop_names(headers: Iterable[tuple[str, str]]) -> frozenset[str]:
    """Hop-by-hop header names for this message: the fixed set plus those listed in `Connection`."""
    named = {
        token.strip().lower()
        for name, value in headers
        if name.lower() == "connection"
        for token in value.split(",")
        if token.strip()
    }
    return HOP_BY_HOP | named


@dataclass(frozen=True, slots=True)
class ForwardInfo:
    """What the transformer needs to know about the inbound request."""

    developer_slug: str
    scheme: str  # "http" | "https" as seen by the client (after Uvicorn's proxy-headers handling)
    host: str | None  # the Host header the client used (Mockan's own host)
    client_ip: str | None
    path_prefix: str = ""  # where a reverse proxy mounts Mockan, e.g. "/mock" (from PUBLIC_BASE_URL)


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, (parts.hostname or "").lower(), parts.port or _DEFAULT_PORTS.get(scheme)


def origin_of(url: str) -> str:
    """`https://host[:port]` of `url`, as the Panel and `RewriteOrigin` spell it."""
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.rpartition('@')[2].lower()}"


def build_request_headers(
    headers: Sequence[tuple[str, str]],
    *,
    info: ForwardInfo,
    upstream_host: str,
    extra_headers: Mapping[str, str] | None = None,
    rewrite_origin_to: str | None = None,
    websocket: bool = False,
) -> HeaderList:
    """The headers to send upstream (arch §6.3: Host, hop-by-hop, X-Forwarded-*, ExtraHeaders...).

    `upstream_host` is the `host[:port]` of the destination. `rewrite_origin_to` (the Service's
    `RewriteOrigin` flag) replaces `Origin` and `Referer`, when the client sent them, with the
    upstream origin.
    """
    dropped = hop_by_hop_names(headers) | _REPLACED_ON_REQUEST | _DROPPED_ON_REQUEST
    if websocket:
        dropped |= _WEBSOCKET_HANDSHAKE
    chain = [value for name, value in headers if name.lower() == "x-forwarded-for"]

    out: HeaderList = [("host", upstream_host)]
    for name, value in headers:
        lowered = name.lower()
        if lowered in dropped or _is_proxy_header(lowered) or lowered == "x-forwarded-for":
            continue
        if rewrite_origin_to is not None and lowered == "origin":
            value = rewrite_origin_to
        elif rewrite_origin_to is not None and lowered == "referer":
            value = rewrite_origin_to + "/"
        out.append((lowered, value))

    forwarded_for = ", ".join(chain)
    if info.client_ip and not forwarded_for.endswith(info.client_ip):
        forwarded_for = f"{forwarded_for}, {info.client_ip}" if forwarded_for else info.client_ip
    if forwarded_for:
        out.append(("x-forwarded-for", forwarded_for))
    out.append(("x-forwarded-proto", info.scheme))
    if info.host:
        out.append(("x-forwarded-host", info.host))
    out.append(("x-forwarded-prefix", f"{info.path_prefix}/{info.developer_slug}"))
    out.append(("x-mockan-developer", info.developer_slug))

    if extra_headers:  # the Service's configured headers win over whatever the client sent
        replaced = {name.lower() for name in extra_headers}
        out = [(name, value) for name, value in out if name not in replaced]
        out.extend((name.lower(), value) for name, value in extra_headers.items())
    return out


@dataclass(frozen=True, slots=True)
class RouteMapping:
    """How an upstream URL path maps back into the client's (Mockan) URL space.

    The inverse of the request rewrite: the path of `public_base_url` (a reverse proxy's mount point,
    e.g. `/mock`) + `/{slug}` + (the Service prefix when `strip_prefix`) + the upstream path below
    the environment's `BaseUrl` path.
    """

    developer_slug: str
    public_base_url: str
    upstream_base_url: str
    service_prefix: str
    strip_prefix: bool

    @property
    def public_path_prefix(self) -> str:
        return urlsplit(self.public_base_url).path.rstrip("/")

    def to_gateway_path(self, upstream_path: str, *, root_without_slash: bool = False) -> str:
        base_path = urlsplit(self.upstream_base_url).path.rstrip("/")
        remainder = upstream_path or "/"
        if base_path and (remainder == base_path or remainder.startswith(base_path + "/")):
            remainder = remainder[len(base_path) :] or "/"
        if root_without_slash and remainder == "/":
            remainder = ""
        prefix = routing_prefix(self.service_prefix) if self.strip_prefix else ""
        return f"{self.public_path_prefix}/{self.developer_slug}{prefix}{remainder}"

    def rewrite_location(self, location: str) -> str:
        """A `Location` that points at the upstream becomes one that points at Mockan."""
        parts = urlsplit(location)
        if parts.scheme or parts.netloc:  # absolute, or protocol-relative (`//host/x`)
            scheme = parts.scheme or urlsplit(self.upstream_base_url).scheme
            if _origin(f"{scheme}://{parts.netloc}") != _origin(self.upstream_base_url):
                return location
            prefix = origin_of(self.public_base_url)  # the mount path comes from to_gateway_path
        elif location.startswith("/"):  # path-absolute: relative to the upstream's root
            prefix = ""
        else:  # path-relative: the browser resolves it inside Mockan's URL space already
            return location
        rewritten = prefix + self.to_gateway_path(parts.path or "/")
        if parts.query:
            rewritten += "?" + parts.query
        if parts.fragment:
            rewritten += "#" + parts.fragment
        return rewritten

    def rewrite_set_cookie(self, value: str) -> str:
        """Drop `Domain` (the cookie belongs to Mockan's host) and move `Path` under the slug.

        Apps use bearer tokens (OQ-02, resolved), so cookies are not on the critical path.
        Known limit: `__Host-` cookies require `Path=/`; they can't survive a path prefix.
        """
        first, *attributes = (part.strip() for part in value.split(";"))
        kept = [first]
        path: str | None = None
        for attribute in attributes:
            name, _, attr_value = attribute.partition("=")
            lowered = name.strip().lower()
            if lowered == "domain":
                continue
            if lowered == "path":
                path = attr_value.strip()
            elif attribute:
                kept.append(attribute)
        mapped = self.to_gateway_path(
            path if path and path.startswith("/") else "/", root_without_slash=True
        )
        kept.append(f"Path={mapped}")
        return "; ".join(kept)


def build_response_headers(headers: Sequence[tuple[str, str]], mapping: RouteMapping) -> HeaderList:
    """The headers to send the client for a proxied response (arch §6.3).

    Hop-by-hop headers and the upstream's own CORS headers are dropped (Mockan's CORS middleware
    adds its own, D-13), `Location` and `Set-Cookie` are rewritten into Mockan's URL space, and
    `X-Mockan-Source: proxy` is added (PR-09). `Content-Length` and `Content-Encoding` are kept:
    the body is passed through raw, so both still describe it.
    """
    dropped = hop_by_hop_names(headers) | _DROPPED_ON_RESPONSE
    out: HeaderList = []
    for name, value in headers:
        lowered = name.lower()
        if lowered in dropped or _is_proxy_header(lowered) or lowered.startswith("access-control-"):
            continue
        if lowered == "location":
            value = mapping.rewrite_location(value)
        elif lowered == "set-cookie":
            value = mapping.rewrite_set_cookie(value)
        out.append((lowered, value))
    out.append(("x-mockan-source", SOURCE_PROXY))
    return out
