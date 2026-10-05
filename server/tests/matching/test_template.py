import pytest

from mockan.matching.errors import PatternError
from mockan.matching.template import parse_template


@pytest.mark.req("FR-05")
def test_param_matches_exactly_one_non_empty_segment() -> None:
    template = parse_template("/orders/{id}")
    assert template.match("/orders/42") == {"id": "42"}
    assert template.match("/orders") is None
    assert template.match("/orders/") is None  # trailing slash is ignored, so no segment
    assert template.match("/orders/42/items") is None
    assert template.match("/orders//items") is None


@pytest.mark.req("FR-05")
def test_empty_middle_segment_does_not_match_a_param() -> None:
    assert parse_template("/a/{x}/b").match("/a//b") is None


@pytest.mark.req("FR-05")
def test_literals_are_case_insensitive_and_captures_keep_case() -> None:
    assert parse_template("/Orders/{Id}").match("/ORDERS/AbC") == {"Id": "AbC"}


@pytest.mark.req("FR-05")
def test_trailing_slash_is_ignored_on_the_path_and_the_pattern() -> None:
    assert parse_template("/orders/{id}/").match("/orders/7/") == {"id": "7"}


@pytest.mark.req("FR-05")
def test_rest_param_matches_zero_or_more_segments() -> None:
    template = parse_template("/files/{*rest}")
    assert template.match("/files") == {"rest": ""}
    assert template.match("/files/") == {"rest": ""}
    assert template.match("/files/a") == {"rest": "a"}
    assert template.match("/files/a/B/c") == {"rest": "a/B/c"}
    assert template.match("/other/a") is None


@pytest.mark.req("FR-05")
def test_root_rest_template_matches_everything() -> None:
    template = parse_template("/{*all}")
    assert template.match("/") == {"all": ""}
    assert template.match("/x/y") == {"all": "x/y"}


@pytest.mark.req("FR-05")
def test_root_template_matches_only_root() -> None:
    template = parse_template("/")
    assert template.match("/") == {}
    assert template.match("/x") is None


@pytest.mark.req("FR-05")
def test_relative_paths_never_match() -> None:
    assert parse_template("/a").match("a") is None


@pytest.mark.req("FR-05")
def test_unicode_literals_and_captures() -> None:
    template = parse_template("/café/{name}")
    assert template.match("/CAFÉ/Zoë") == {"name": "Zoë"}


@pytest.mark.req("FR-05")
def test_percent_signs_are_literal_characters() -> None:
    # The matcher sees the decoded path from ASGI, so it never decodes again.
    assert parse_template("/a%20b/{x}").match("/a%20b/1") == {"x": "1"}
    assert parse_template("/a%20b/{x}").match("/a b/1") is None


@pytest.mark.req("FR-05")
@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("/a/{*rest}/b", "{*name} can only be the last segment."),
        ("/a/{id}/{id}", "Parameter {id} is used twice."),
        ("/a/{id}/{*id}", "Parameter {id} is used twice."),
        ("/a/x{id}", "“x{id}” isn't valid. Use {name} or {*name} as a whole segment."),
        ("/a/{}", "“{}” isn't valid. Use {name} or {*name} as a whole segment."),
        ("/a/{1x}", "“{1x}” isn't valid. Use {name} or {*name} as a whole segment."),
        ("/a/{id", "“{id” isn't valid. Use {name} or {*name} as a whole segment."),
    ],
)
def test_invalid_templates_are_rejected(pattern: str, message: str) -> None:
    with pytest.raises(PatternError) as error:
        parse_template(pattern)
    assert error.value.field == "pattern"
    assert error.value.message == message
