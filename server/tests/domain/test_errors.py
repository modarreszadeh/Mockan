import re

from mockan.domain.errors import ErrorCode


def test_error_codes_are_unique_snake_case_and_match_their_names() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))
    for code in ErrorCode:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", code.value)
        assert code.name == code.value.upper()


def test_gateway_codes_from_arch_rule_8_exist() -> None:
    expected = {
        "developer_not_found",
        "service_not_resolved",
        "upstream_unreachable",
        "upstream_timeout",
        "mock_render_failed",
    }
    assert expected <= {code.value for code in ErrorCode}
