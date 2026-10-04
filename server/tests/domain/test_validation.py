import pytest

from mockan.domain.validation import host_is_allowed, is_reserved_slug, is_valid_slug


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
