from datetime import UTC, datetime

import pytest

from mockan.domain.enums import MatchType
from mockan.matching.matcher import match_request
from mockan.matching.model import RequestFacts
from tests.support.snapshot_builder import SnapshotBuilder, equals, exists, facts


def _winner(builder: SnapshotBuilder, slug_index: int = 0, **kwargs: object) -> str | None:
    snapshot = builder.build()
    developer = list(snapshot.developers_by_slug.values())[slug_index]
    result = match_request(snapshot.rules_for(developer.id), facts(**kwargs))  # type: ignore[arg-type]
    return result.rule.name if result else None


@pytest.mark.req("PR-05")
@pytest.mark.parametrize(
    ("match_type", "pattern", "path", "expected"),
    [
        (MatchType.EXACT, "/limsa/api/v1/dashboard", "/limsa/api/v1/dashboard", True),
        (MatchType.EXACT, "/limsa/api/v1/dashboard", "/LIMSA/api/v1/dashboard/", True),
        (MatchType.EXACT, "/limsa/api/v1/dashboard", "/limsa/api/v1/dashboard/x", False),
        (MatchType.EXACT, "/", "/", True),
        (MatchType.EXACT, "/", "/x", False),
        (MatchType.EXACT, "/café", "/CAFÉ", True),
        (MatchType.TEMPLATE, "/orders/{id}", "/orders/42", True),
        (MatchType.TEMPLATE, "/orders/{id}", "/orders", False),
        (MatchType.TEMPLATE, "/files/{*rest}", "/files", True),
        (MatchType.TEMPLATE, "/files/{*rest}", "/files/a/b", True),
        (MatchType.PREFIX, "/reports/", "/reports/2026/q1", True),
        (MatchType.PREFIX, "/reports/", "/other", False),
        (MatchType.REGEX, r"^/items/\d+$", "/items/9", True),
        (MatchType.REGEX, r"^/items/\d+$", "/items/x", False),
    ],
)
def test_every_match_type(
    snapshot_builder: SnapshotBuilder,
    match_type: MatchType,
    pattern: str,
    path: str,
    expected: bool,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, match_type, pattern, name="r")
    assert (_winner(snapshot_builder, path=path) == "r") is expected


@pytest.mark.req("FR-05")
def test_the_result_carries_captured_params_and_a_reason(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.TEMPLATE, "/orders/{id}", name="order", priority=5)
    snapshot = snapshot_builder.build()
    result = match_request(snapshot.rules_for(dev.id), facts("/orders/42"))
    assert result is not None
    assert result.params == {"id": "42"}
    assert result.reason == "Template rule “order” (/orders/{id}) won with priority 5"
    assert result.rule.active_response is not None


@pytest.mark.req("PR-05")
def test_no_rules_or_no_match_returns_none(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot = snapshot_builder.build()
    assert match_request(snapshot.rules_for(dev.id), facts("/x")) is None
    snapshot_builder.rule(dev, MatchType.EXACT, "/y")
    assert _winner(snapshot_builder, path="/x") is None


@pytest.mark.req("PR-05")
def test_method_filter_and_any(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="get-only", method="GET")
    snapshot_builder.rule(dev, MatchType.EXACT, "/b", name="any")
    assert _winner(snapshot_builder, path="/a", method="get") == "get-only"
    assert _winner(snapshot_builder, path="/a", method="POST") is None
    assert _winner(snapshot_builder, path="/b", method="DELETE") == "any"


@pytest.mark.req("PR-05")
def test_head_does_not_match_a_get_rule(snapshot_builder: SnapshotBuilder) -> None:
    # OQ-B5 default
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="get-only", method="GET")
    assert _winner(snapshot_builder, path="/a", method="HEAD") is None


@pytest.mark.req("PR-05")
def test_query_conditions(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev,
        MatchType.EXACT,
        "/search",
        name="q",
        query=[equals("page", "2"), exists("debug")],
    )
    both = {"page": ["1", "2"], "debug": [""]}  # equals = any value equals; exists ignores value
    assert _winner(snapshot_builder, path="/search", query=both) == "q"
    assert _winner(snapshot_builder, path="/search", query={"page": ["2"]}) is None
    assert _winner(snapshot_builder, path="/search", query={"page": ["3"], "debug": ["1"]}) is None
    assert _winner(snapshot_builder, path="/search", query={"page": [], "debug": ["1"]}) is None
    assert _winner(snapshot_builder, path="/search") is None


@pytest.mark.req("PR-05")
def test_header_conditions_names_are_case_insensitive_and_values_case_sensitive(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev,
        MatchType.EXACT,
        "/h",
        name="h",
        headers=[equals("X-Env", "Dev"), exists("Authorization")],
    )
    ok = {"x-env": "Dev", "AUTHORIZATION": "Bearer t"}
    assert _winner(snapshot_builder, path="/h", headers=ok) == "h"
    assert _winner(snapshot_builder, path="/h", headers={**ok, "x-env": "dev"}) is None
    assert _winner(snapshot_builder, path="/h", headers={"x-env": "Dev"}) is None
    assert _winner(snapshot_builder, path="/h") is None


@pytest.mark.req("PR-05")
def test_precedence_priority_first(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="exact")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/", name="prefix-p1", priority=1)
    assert _winner(snapshot_builder, path="/a") == "prefix-p1"


@pytest.mark.req("PR-05")
def test_precedence_match_type_rank(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.REGEX, "^/a/b$", name="regex")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/a/b", name="prefix")
    snapshot_builder.rule(dev, MatchType.TEMPLATE, "/a/{x}", name="template")
    assert _winner(snapshot_builder, path="/a/b") == "template"
    snapshot_builder.rule(dev, MatchType.EXACT, "/a/b", name="exact")
    assert _winner(snapshot_builder, path="/a/b") == "exact"


@pytest.mark.req("PR-05")
def test_precedence_longer_pattern(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/a/", name="short")
    snapshot_builder.rule(dev, MatchType.PREFIX, "/a/b/", name="long")
    assert _winner(snapshot_builder, path="/a/b/c") == "long"


@pytest.mark.req("PR-05")
def test_precedence_older_rule(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev, MatchType.EXACT, "/a", name="newer", created_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    snapshot_builder.rule(
        dev, MatchType.EXACT, "/a", name="older", created_at=datetime(2026, 5, 1, tzinfo=UTC)
    )
    assert _winner(snapshot_builder, path="/a") == "older"


@pytest.mark.req("PR-05")
def test_a_losing_rule_that_matches_does_not_replace_the_winner(
    snapshot_builder: SnapshotBuilder,
) -> None:
    # Unsorted input: the better rule comes last and must still win, the worse one first.
    dev = snapshot_builder.developer("ehtesham")
    worse = snapshot_builder.rule(dev, MatchType.PREFIX, "/", name="worse")
    better = snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="better")
    again_worse = snapshot_builder.rule(dev, MatchType.REGEX, "^/", name="again-worse")
    request = facts("/a")
    for ordering in (
        [worse, better, again_worse],
        [better, worse, again_worse],
        [again_worse, worse, better],
    ):
        result = match_request(ordering, request)
        assert result is not None
        assert result.rule.name == "better"


@pytest.mark.req("PR-05")
def test_equal_sort_keys_keep_the_first_rule(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    first = snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="first", created_at=moment)
    second = snapshot_builder.rule(dev, MatchType.EXACT, "/a", name="second", created_at=moment)
    result = match_request([first, second], facts("/a"))
    assert result is not None
    assert result.rule.name == "first"


@pytest.mark.req("PR-01")
def test_developers_are_isolated(snapshot_builder: SnapshotBuilder) -> None:
    a = snapshot_builder.developer("alice")
    b = snapshot_builder.developer("bob")
    snapshot_builder.rule(a, MatchType.EXACT, "/limsa/x", name="alice-rule", status=201)
    snapshot_builder.rule(b, MatchType.EXACT, "/limsa/x", name="bob-rule", status=202)
    snapshot = snapshot_builder.build()
    request: RequestFacts = facts("/limsa/x")
    alice = match_request(snapshot.rules_for(a.id), request)
    bob = match_request(snapshot.rules_for(b.id), request)
    assert alice is not None
    assert bob is not None
    assert (alice.rule.name, bob.rule.name) == ("alice-rule", "bob-rule")
    assert (
        match_request(snapshot.rules_for(snapshot_builder.developer("carol").id), request) is None
    )


@pytest.mark.req("NFR-01")
@pytest.mark.parametrize(
    ("match_type", "pattern", "path"),
    [
        (MatchType.EXACT, "/Limsa/Api", "/LIMSA/api/"),
        (MatchType.PREFIX, "/Limsa/", "/LIMSA/x"),
        (MatchType.TEMPLATE, "/Files/{*rest}", "/files"),
        (MatchType.TEMPLATE, "/Orders/{id}", "/ORDERS/1"),
        (MatchType.EXACT, "/café", "/CAFÉ"),
        (MatchType.REGEX, r"^/Items/\d+$", "/Items/5"),
        (MatchType.REGEX, r"(?i)^/items/\d+$", "/ITEMS/5"),
    ],
)
def test_the_literal_prefix_prefilter_never_hides_a_real_match(
    snapshot_builder: SnapshotBuilder, match_type: MatchType, pattern: str, path: str
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, match_type, pattern, name="r")
    assert _winner(snapshot_builder, path=path) == "r"


@pytest.mark.req("PR-05")
def test_anchored_regex_stays_case_sensitive_despite_the_prefilter(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(dev, MatchType.REGEX, r"^/Items/\d+$", name="r")
    assert _winner(snapshot_builder, path="/items/5") is None  # OQ-B3
