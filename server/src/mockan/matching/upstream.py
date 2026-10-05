"""Where a request goes upstream: the path and URL, shared by the Gateway and test-route (FR-10)."""

from urllib.parse import quote, unquote

from mockan.domain.validation import routing_prefix

# RFC 3986 `pchar` minus `%`: used only when the client's raw path can't be reused as is.
_PATH_SAFE = "/:@!$&'()*+,;="


def build_upstream_path(
    *,
    raw_path: str | None,
    upstream_path: str,
    service_prefix: str,
    strip_prefix: bool,
) -> str:
    """The path to request upstream, byte-faithful to what the client sent when possible (PR-02).

    `upstream_path` is what `resolve_service` computed from the *decoded* path (the Developer slug
    removed and, with `strip_prefix`, the Service prefix too). The raw path keeps percent-encoding
    such as `%2F` that decoding would destroy, so it is reused whenever it agrees with that result;
    otherwise the decoded result is re-encoded.
    """
    service_prefix = routing_prefix(service_prefix)
    if raw_path:
        _, _, tail = raw_path[1:].partition("/")  # drop the Developer slug segment
        candidate = "/" + tail
        if strip_prefix:
            head, rest = candidate[: len(service_prefix)], candidate[len(service_prefix) :]
            # An encoded prefix (`/lim%73a`) or a different boundary: the raw bytes don't line up.
            aligned = head.lower() == service_prefix.lower() and (not rest or rest[0] == "/")
            candidate = (rest or "/") if aligned else ""
        if candidate and unquote(candidate) == upstream_path:
            return candidate
    return quote(upstream_path, safe=_PATH_SAFE)


def build_upstream_url(base_url: str, upstream_path: str, raw_query: str) -> str:
    """`BaseUrl` + path (+ the raw query string, never re-encoded)."""
    url = base_url.rstrip("/") + upstream_path
    return f"{url}?{raw_query}" if raw_query else url
