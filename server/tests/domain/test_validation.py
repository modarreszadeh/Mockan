import pytest

from mockan.domain.validation import (
    host_is_allowed,
    is_reserved_slug,
    is_valid_slug,
    origin_is_allowed,
)


@pytest.mark.req("PR-01")
@pytest.mark.parametrize("slug", ["ab", "ehtesham", "a1-b2", "a" * 32])
def test_valid_slugs(slug: str) -> None:
    assert is_valid_slug(slug)


@pytest.mark.req("PR-01")
@pytest.mark.parametrize("slug", ["", "a", "Ab", "1ab", "-ab", "a_b", "a" * 33, "ab\n", "ab cd"])
def test_invalid_slugs(slug: str) -> None:
    assert not is_valid_slug(slug)


@pytest.mark.req("PR-01")
@pytest.mark.parametrize(
    ("slug", "reserved"),
    [
        ("api", True),
        ("hubs", True),
        ("health", True),
        ("_mockan", True),
        ("_x", True),
        ("ehtesham", False),
    ],
)
def test_reserved_slugs(slug: str, reserved: bool) -> None:
    assert is_reserved_slug(slug) is reserved


@pytest.mark.req("PR-15")
@pytest.mark.parametrize(
    ("host", "patterns", "allowed"),
    [
        ("identity.stage.internal", ["identity.stage.internal"], True),
        ("IDENTITY.stage.INTERNAL", ["identity.stage.internal"], True),
        ("identity.stage.internal:8443", ["identity.stage.internal"], True),
        ("identity.stage.internal", ["identity.stage.internal:443"], True),
        ("identity.stage.internal.", ["identity.stage.internal"], True),
        ("a.dev.internal", ["*.dev.internal"], True),
        ("a.b.dev.internal", ["*.dev.internal"], True),
        ("dev.internal", ["*.dev.internal"], False),  # wildcard never matches the apex
        (".dev.internal", ["*.dev.internal"], False),
        ("evildev.internal", ["*.dev.internal"], False),
        ("a.dev.internal.evil.com", ["*.dev.internal"], False),
        ("prod.internal", ["identity.stage.internal", "*.dev.internal"], False),
        ("", ["*.dev.internal"], False),
        ("anything", [], False),
        ("[::1]:8080", ["[::1]"], True),
        ("[::1", ["[::1"], True),
        ("::1", ["::1"], True),
    ],
)
def test_host_is_allowed(host: str, patterns: list[str], allowed: bool) -> None:
    assert host_is_allowed(host, patterns) is allowed


@pytest.mark.req("PR-03")
@pytest.mark.parametrize(
    ("origin", "patterns", "allowed"),
    [
        ("http://localhost:5173", ["http://localhost:*"], True),
        ("http://localhost", ["http://localhost:*"], True),  # default port: no port in the header
        ("http://127.0.0.1:3000", ["http://localhost:*", "http://127.0.0.1:*"], True),
        ("HTTP://LocalHost:5173", ["http://localhost:*"], True),
        ("http://localhost:5173", ["http://localhost:5173"], True),
        ("http://localhost:5174", ["http://localhost:5173"], False),
        ("http://localhost", ["http://localhost:5173"], False),
        ("http://localhost:5173", ["http://localhost"], False),
        ("https://localhost:5173", ["http://localhost:*"], False),  # scheme differs
        ("http://localhost:1.evil.com", ["http://localhost:*"], False),  # not a glob
        ("http://localhost.evil.com:80", ["http://localhost:*"], False),
        ("http://evil.com/http://localhost:1", ["http://localhost:*"], False),
        ("https://app.example.com", ["https://*.example.com"], True),
        ("https://a.b.example.com", ["https://*.example.com"], True),
        ("https://example.com", ["https://*.example.com"], False),  # never the apex
        ("https://evilexample.com", ["https://*.example.com"], False),
        ("http://[::1]:8080", ["http://[::1]:*"], True),
        ("null", ["http://localhost:*"], False),
        ("", ["http://localhost:*"], False),
        ("http://*", ["http://*"], False),  # wildcards in the request origin never match
        ("http://localhost:5173", ["not-an-origin", "http://localhost:*"], True),
        ("http://localhost:5173", [], False),
    ],
)
def test_origin_is_allowed(origin: str, patterns: list[str], allowed: bool) -> None:
    assert origin_is_allowed(origin, patterns) is allowed
