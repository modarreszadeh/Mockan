"""Pure validation rules shared by the Admin (save time) and the Gateway (defence in depth)."""

import re
from collections.abc import Iterable

from mockan.domain.constants import RESERVED_SLUGS, SLUG_REGEX


def is_valid_slug(slug: str) -> bool:
    return SLUG_REGEX.fullmatch(slug) is not None


def is_reserved_slug(slug: str) -> bool:
    return slug.startswith("_") or slug in RESERVED_SLUGS


def _strip_port(host: str) -> str:
    if host.startswith("["):  # [::1]:8080
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _normalise_host(host: str) -> str:
    return _strip_port(host.strip()).lower().rstrip(".")


def host_is_allowed(host: str, patterns: Iterable[str]) -> bool:
    """Is `host` allowed by `patterns`? Case-insensitive, ports ignored.

    A `*.example.com` pattern matches subdomains only, never `example.com` itself (NFR-06).
    """
    candidate = _normalise_host(host)
    if not candidate:
        return False
    for raw in patterns:
        pattern = _normalise_host(raw)
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            if candidate.endswith(suffix) and len(candidate) > len(suffix):
                return True
        elif candidate == pattern:
            return True
    return False


_ORIGIN = re.compile(r"(?i)(https?)://(\*\.[^/:*]+|[^/:*\s]+|\[[^\]]+\])(?::(\*|\d+))?")


def origin_is_allowed(origin: str, patterns: Iterable[str]) -> bool:
    """Is a request `Origin` allowed by the Developer's `allowedOrigins` (D-13)?

    Patterns are `scheme://host[:port]` where the port may be `*` (any, or none) and the host may
    be `*.example.com` (subdomains only). Unlike a plain glob, `http://localhost:*` can never match
    `http://localhost:1.evil.com`: scheme, host and port are compared separately.
    """
    parsed = _ORIGIN.fullmatch(origin.strip())
    if parsed is None or "*" in origin:
        return False
    scheme, host, port = parsed.group(1).lower(), parsed.group(2).lower(), parsed.group(3)
    for raw in patterns:
        wanted = _ORIGIN.fullmatch(raw.strip())
        if wanted is None:
            continue
        want_scheme, want_host, want_port = (
            wanted.group(1).lower(),
            wanted.group(2).lower(),
            wanted.group(3),
        )
        if want_scheme != scheme:
            continue
        if want_host.startswith("*."):
            suffix = want_host[1:]
            if not (host.endswith(suffix) and len(host) > len(suffix)):
                continue
        elif want_host != host:
            continue
        if want_port == "*" or want_port == port:
            return True
    return False
