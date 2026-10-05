import json

import pytest
import structlog

from mockan.infrastructure.logging import bind_log_context, clear_log_context, configure_logging
from mockan.infrastructure.masking import MASK, is_sensitive_name, mask_headers, mask_json


@pytest.mark.req("NFR-07")
@pytest.mark.parametrize(
    ("name", "sensitive"),
    [
        ("Authorization", True),
        ("authorization", True),
        ("Proxy-Authorization", True),
        ("Cookie", True),
        ("Set-Cookie", True),
        ("X-Api-Key", True),
        ("x_api_key", True),
        ("apikey", True),
        ("access_token", True),
        ("clientSecret", True),
        ("password", True),
        ("X-Auth-Token", True),
        ("Content-Type", False),
        ("Accept", False),
        ("X-Request-Id", False),
    ],
)
def test_sensitive_names(name: str, sensitive: bool) -> None:
    assert is_sensitive_name(name) is sensitive


@pytest.mark.req("NFR-07")
def test_mask_headers_keeps_the_rest_untouched() -> None:
    headers = {"Authorization": "Bearer abc", "Cookie": "s=1", "Accept": "*/*", "X-Api-Key": "k"}
    assert mask_headers(headers) == {
        "Authorization": MASK,
        "Cookie": MASK,
        "Accept": "*/*",
        "X-Api-Key": MASK,
    }
    assert headers["Authorization"] == "Bearer abc"  # input is not mutated


@pytest.mark.req("NFR-07")
def test_mask_json_is_recursive_and_copies() -> None:
    original = {
        "user": "ann",
        "password": "hunter2",
        "nested": {"refresh_token": "t", "items": [{"secret": "s", "ok": 1}, "plain", 3]},
        "pair": ("a", {"apiKey": "k"}),
        1: "numeric key",
        "none": None,
    }
    assert mask_json(original) == {
        "user": "ann",
        "password": MASK,
        "nested": {"refresh_token": MASK, "items": [{"secret": MASK, "ok": 1}, "plain", 3]},
        "pair": ["a", {"apiKey": MASK}],
        "1": "numeric key",
        "none": None,
    }
    assert original["password"] == "hunter2"


@pytest.mark.req("NFR-07")
def test_log_lines_are_masked_and_carry_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    clear_log_context()
    bind_log_context(developer="ehtesham", rule_id="r1")
    structlog.get_logger().info(
        "request_proxied", headers={"Authorization": "Bearer abc", "Accept": "*/*"}, token="zzz"
    )
    structlog.get_logger().debug("hidden")
    clear_log_context()
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    assert len(lines) == 1
    line = lines[0]
    assert line["event"] == "request_proxied"
    assert line["level"] == "info"
    assert line["developer"] == "ehtesham"
    assert line["headers"] == {"Authorization": MASK, "Accept": "*/*"}
    assert line["token"] == MASK
    assert "abc" not in json.dumps(line)
    assert "timestamp" in line


def test_console_format_and_unknown_level_fall_back_sanely(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("NOPE", "console")
    structlog.get_logger().info("hello_console", password="x")
    out = capsys.readouterr().out
    assert "hello_console" in out
    assert "password" in out
    assert MASK in out
    configure_logging("INFO", "json")
