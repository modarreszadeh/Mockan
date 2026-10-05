"""Pure validation rules shared by the Admin (save time) and the Gateway (defence in depth)."""

import re
from collections.abc import Iterable

from mockan.domain.constants import MAX_ORIGIN_LENGTH, RESERVED_SLUGS, SLUG_REGEX


def is_valid_slug(slug: str) -> bool:
    return SLUG_REGEX.fullmatch(slug) is not None


def is_reserved_slug(slug: str) -> bool:
    return slug.startswith("_") or slug in RESERVED_SLUGS


def slug_problem(slug: str) -> str | None:
    """Why a DeveloperSlug is invalid, or `None`. Messages match the Panel's `slugProblem`."""
    if not slug:
        return "Enter a slug."
    if slug.startswith("_"):
        return "Slugs starting with “_” are reserved for Mockan."
    if slug in RESERVED_SLUGS:
        return f"“{slug}” is reserved. Pick another slug."
    if any(char.isupper() for char in slug):
        return "Use lowercase letters only."
    if not ("a" <= slug[0] <= "z"):
        return "Start with a lowercase letter."
    if len(slug) < 2:
        return "Use at least 2 characters."
    if len(slug) > 32:
        return "Use at most 32 characters."
    if not is_valid_slug(slug):
        return "Use only lowercase letters, digits and hyphens."
    return None


def _strip_port(host: str) -> str:
    if host.startswith("["):  # [::1]:8080
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _normalise_host(host: str) -> str:
    return _strip_port(host.strip()).lower().rstrip(".")


def routing_prefix(path_prefix: str) -> str:
    """The prefix to slice or join with: `/` (the catch-all Service) is the empty prefix.

    Otherwise stripping `/` would eat the leading slash of the path and joining it would give `//`.
    """
    return "" if path_prefix == "/" else path_prefix


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


def origin_problem(origin: str) -> str | None:
    """Why an `allowedOrigins` entry is invalid, or `None`.

    Stricter than the Panel's check: it must be a complete `scheme://host[:port|:*]` pattern,
    which is what `origin_is_allowed` can use.
    """
    value = origin.strip()
    if not value:
        return "Enter an origin."
    if not value.lower().startswith(("http://", "https://")):
        return "Start with http:// or https://."
    if re.search(r"\s", value):
        return "Origins can't contain spaces."
    if value.endswith("/") or re.match(r"(?i)https?://[^/]+/.", value):
        return "Use scheme, host and port only — no path."
    if len(value) > MAX_ORIGIN_LENGTH:
        return f"Use at most {MAX_ORIGIN_LENGTH} characters."
    if _ORIGIN.fullmatch(value) is None:
        return "Use the form scheme://host[:port], e.g. http://localhost:*."
    return None


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
