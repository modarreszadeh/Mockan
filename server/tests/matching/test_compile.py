import uuid
from datetime import UTC, datetime

import pytest

from mockan.domain.enums import BodyMode, ConditionOperator, MatchType
from mockan.matching.compile import (
    compile_pattern,
    compile_response,
    compile_rule,
    literal_prefix,
)
from mockan.matching.errors import PatternError
from mockan.matching.model import Condition


def _error(match_type: MatchType, pattern: str) -> PatternError:
    with pytest.raises(PatternError) as error:
        compile_pattern(match_type, pattern)
    return error.value


@pytest.mark.req("PR-05")
def test_exact_ignores_case_and_one_trailing_slash() -> None:
    matcher = compile_pattern(MatchType.EXACT, "/Limsa/Api/")
    assert matcher.match("/limsa/api") == {}
    assert matcher.match("/LIMSA/API/") == {}
    assert matcher.match("/limsa/api/x") is None
    assert matcher.match("/limsa/apix") is None


@pytest.mark.req("PR-05")
def test_exact_root() -> None:
    matcher = compile_pattern(MatchType.EXACT, "/")
    assert matcher.match("/") == {}
    assert matcher.match("/a") is None


@pytest.mark.req("PR-05")
def test_prefix_is_case_insensitive_and_literal() -> None:
    matcher = compile_pattern(MatchType.PREFIX, "/limsa/api/v1/reports/")
    assert matcher.match("/LIMSA/api/v1/reports/2026") == {}
    assert matcher.match("/limsa/api/v1/reports") is None  # arch §7.1: starts with the pattern
    assert matcher.match("/limsa/api/v1/other") is None


@pytest.mark.req("PR-05")
def test_regex_uses_search_semantics_on_the_original_case_path() -> None:
    matcher = compile_pattern(MatchType.REGEX, r"^/limsa/api/v1/(items|goods)/\d+$")
    assert matcher.match("/limsa/api/v1/items/7") == {}
    assert matcher.match("/limsa/api/v1/goods/7/x") is None
    assert matcher.match("/LIMSA/api/v1/items/7") is None  # OQ-B3: original case
    assert compile_pattern(MatchType.REGEX, r"(?i)^/limsa$").match("/LIMSA") == {}
    assert compile_pattern(MatchType.REGEX, r"orders").match("/a/orders/1") == {}  # unanchored


@pytest.mark.req("PR-05")
def test_regex_named_groups_become_params_and_unmatched_groups_are_dropped() -> None:
    matcher = compile_pattern(MatchType.REGEX, r"^/o/(?P<id>\d+)(?:/(?P<tail>x))?$")
    assert matcher.match("/o/5") == {"id": "5"}
    assert matcher.match("/o/5/x") == {"id": "5", "tail": "x"}


@pytest.mark.req("PR-05")
def test_template_pattern_compiles_through_the_same_entry_point() -> None:
    assert compile_pattern(MatchType.TEMPLATE, "/o/{id}").match("/o/1") == {"id": "1"}


@pytest.mark.req("NFR-08")
@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        (r"^/a/(b)\1$", "RE2 doesn't support backreferences."),
        (r"^/a/\k<x>$", "RE2 doesn't support backreferences."),
        (r"^/a(?=b)", "RE2 doesn't support lookahead or lookbehind."),
        (r"^/a(?!b)", "RE2 doesn't support lookahead or lookbehind."),
        (r"(?<=a)b", "RE2 doesn't support lookahead or lookbehind."),
        (r"(?<!a)b", "RE2 doesn't support lookahead or lookbehind."),
        ("a" * 513, "Regex patterns can be at most 512 characters."),
    ],
)
def test_regex_rejects_what_re2_cannot_run(pattern: str, message: str) -> None:
    error = _error(MatchType.REGEX, pattern)
    assert (error.field, error.message) == ("pattern", message)


@pytest.mark.req("NFR-08")
def test_regex_of_exactly_512_characters_is_accepted() -> None:
    assert compile_pattern(MatchType.REGEX, "a" * 512).match("/" + "a" * 512) == {}


@pytest.mark.req("NFR-08")
def test_regex_syntax_errors_carry_the_re2_message() -> None:
    error = _error(MatchType.REGEX, "(")
    assert error.field == "pattern"
    assert error.message.startswith("Invalid regex: missing )")


@pytest.mark.req("PR-05")
@pytest.mark.parametrize("match_type", list(MatchType))
@pytest.mark.parametrize("pattern", ["", "   "])
def test_empty_patterns_are_rejected(match_type: MatchType, pattern: str) -> None:
    assert _error(match_type, pattern).message == "Enter a pattern."


@pytest.mark.req("PR-05")
@pytest.mark.parametrize("match_type", [MatchType.EXACT, MatchType.TEMPLATE, MatchType.PREFIX])
def test_path_patterns_must_start_with_a_slash_and_have_no_spaces(match_type: MatchType) -> None:
    assert _error(match_type, "limsa").message == "Start the pattern with “/”."
    assert _error(match_type, "/a b").message == "Patterns can't contain spaces."


@pytest.mark.req("PR-05")
@pytest.mark.parametrize("match_type", [MatchType.EXACT, MatchType.PREFIX])
def test_exact_and_prefix_reject_braces(match_type: MatchType) -> None:
    assert _error(match_type, "/a/{id}").message == (
        f"{match_type.value} patterns can't contain {{ or }}. Use Template for parameters."
    )


@pytest.mark.req("PR-05")
def test_compile_rule_normalises_method_and_header_names_and_sets_the_sort_key() -> None:
    created = datetime(2026, 3, 1, tzinfo=UTC)
    rule = compile_rule(
        match_type=MatchType.EXACT,
        pattern="/abc",
        method="get",
        header_conditions=[Condition("  X-Env ", ConditionOperator.EQUALS, "dev")],
        query_conditions=[Condition("Page", ConditionOperator.EXISTS, "ignored")],
        priority=7,
        created_at=created,
    )
    assert rule.method == "GET"
    assert rule.header_conditions == (Condition("x-env", ConditionOperator.EQUALS, "dev"),)
    assert rule.query_conditions == (Condition("Page", ConditionOperator.EXISTS, None),)
    assert rule.sort_key == (7, 0, -4, created)
    assert rule.active_response is None


@pytest.mark.req("PR-05")
def test_compile_rule_picks_the_active_response() -> None:
    first, second = uuid.uuid7(), uuid.uuid7()
    responses = [
        compile_response(
            response_id=rid,
            name=name,
            status_code=200,
            headers={},
            content_type="text/plain",
            body="héllo",
        )
        for rid, name in ((first, "a"), (second, "b"))
    ]
    rule = compile_rule(
        match_type=MatchType.PREFIX, pattern="/", responses=responses, active_response_id=second
    )
    assert rule.active_response is responses[1]
    assert rule.active_response.body_bytes == "héllo".encode()
    assert rule.active_response.body_mode is BodyMode.STATIC
    assert len(rule.responses) == 2


@pytest.mark.req("PR-06")
def test_compile_response_freezes_headers() -> None:
    headers = {"X-A": "1"}
    response = compile_response(
        response_id=uuid.uuid7(),
        name="r",
        status_code=201,
        headers=headers,
        content_type="x",
        body="",
        delay_ms=5,
    )
    headers["X-B"] = "2"
    assert dict(response.headers) == {"X-A": "1"}
    assert response.delay_ms == 5
    with pytest.raises(TypeError):
        response.headers["X-C"] = "3"  # type: ignore[index]


@pytest.mark.req("PR-05")
def test_compile_rule_rejects_blank_condition_keys_and_missing_equals_values() -> None:
    with pytest.raises(PatternError) as blank:
        compile_rule(
            match_type=MatchType.EXACT,
            pattern="/a",
            query_conditions=[Condition(" ", ConditionOperator.EXISTS)],
        )
    assert (blank.value.field, blank.value.message) == ("queryConditions.0.key", "Enter a name.")

    with pytest.raises(PatternError) as missing:
        compile_rule(
            match_type=MatchType.EXACT,
            pattern="/a",
            header_conditions=[
                Condition("a", ConditionOperator.EXISTS),
                Condition("b", ConditionOperator.EQUALS, None),
            ],
        )
    assert (missing.value.field, missing.value.message) == (
        "headerConditions.1.value",
        "Enter a value.",
    )


@pytest.mark.req("PR-05")
def test_compile_rule_reports_the_pattern_field_first() -> None:
    with pytest.raises(PatternError) as error:
        compile_rule(match_type=MatchType.EXACT, pattern="nope")
    assert error.value.field == "pattern"


@pytest.mark.req("NFR-01")
@pytest.mark.parametrize(
    ("match_type", "pattern", "prefix"),
    [
        (MatchType.EXACT, "/Limsa/Api/", "/limsa/api"),
        (MatchType.EXACT, "/", "/"),
        (MatchType.PREFIX, "/Limsa/Reports/", "/limsa/reports/"),
        (MatchType.TEMPLATE, "/Orders/{id}/items", "/orders"),
        (MatchType.TEMPLATE, "/files/{*rest}", "/files"),
        (MatchType.TEMPLATE, "/{*all}", ""),
        (MatchType.TEMPLATE, "/", ""),
        (MatchType.REGEX, "^/Limsa/api", "/limsa/api"),
        (MatchType.REGEX, r"^/a/\d+$", "/a/"),
        (MatchType.REGEX, "^/a?", "/"),
        (MatchType.REGEX, "^/a*b", "/"),
        (MatchType.REGEX, "^/a{2}", "/"),
        (MatchType.REGEX, "^/a(b)", "/a"),
        (MatchType.REGEX, "^/a|^/b", ""),
        (MatchType.REGEX, "^", ""),
        (MatchType.REGEX, "^?", ""),
        (MatchType.REGEX, "^(?i)/a", ""),
        (MatchType.REGEX, "/a$", ""),
    ],
)
def test_literal_prefix_is_a_necessary_condition_for_a_match(
    match_type: MatchType, pattern: str, prefix: str
) -> None:
    assert literal_prefix(match_type, pattern) == prefix
    assert compile_rule(match_type=match_type, pattern=pattern).literal_prefix == prefix
