"""Pure validation rules shared by the Admin (save time) and the Gateway (defence in depth)."""

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
