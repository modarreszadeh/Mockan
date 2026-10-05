"""`POST /me/test-route`: what would happen to this request? (FR-10, PR-13)."""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field

from mockan.admin.schemas.base import CamelInput, CamelModel
from mockan.admin.schemas.common import no_nul
from mockan.admin.schemas.rule import Method
from mockan.domain.enums import MatchType

MAX_PATH = 2048
MAX_ENTRIES = 50
MAX_TEXT = 2000


def _path(value: str) -> str:
    value = no_nul(value)
    if not value.startswith("/"):
        raise ValueError("Start the path with “/”, e.g. /limsa/api/v1/dashboard.")
    if "?" in value or "#" in value:
        raise ValueError("Leave the query string out of the path; use `query`.")
    if len(value) > MAX_PATH:
        raise ValueError(f"Use at most {MAX_PATH} characters.")
    return value


def _text(value: str) -> str:
    if len(value) > MAX_TEXT:
        raise ValueError(f"Use at most {MAX_TEXT} characters.")
    return no_nul(value)


Text = Annotated[str, AfterValidator(_text)]


def _values(value: object) -> list[str]:
    """A query value is one string or a list of strings (a repeated parameter)."""
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError("Use a string, or a list of strings for a repeated parameter.")
    return [_text(item) for item in items]


def _upper(value: object) -> object:
    return value.upper() if isinstance(value, str) else value


class TestRouteIn(CamelInput):
    __test__ = False  # not a pytest class

    method: Annotated[Method, BeforeValidator(_upper)] = "GET"
    path: Annotated[str, AfterValidator(_path)]
    """The path **after** your slug (what rules match), e.g. `/limsa/api/v1/dashboard`."""
    headers: Annotated[dict[Text, Text], Field(max_length=MAX_ENTRIES)] = Field(
        default_factory=dict
    )
    query: Annotated[
        dict[Text, Annotated[list[str], BeforeValidator(_values)]], Field(max_length=MAX_ENTRIES)
    ] = Field(default_factory=dict)


class MatchedResponseOut(CamelModel):
    id: uuid.UUID
    name: str
    status_code: int
    delay_ms: int


class MatchedRuleOut(CamelModel):
    id: uuid.UUID
    name: str
    method: str
    match_type: MatchType
    pattern: str
    priority: int
    active_response: MatchedResponseOut


class RoutedServiceOut(CamelModel):
    id: uuid.UUID
    name: str
    environment: str


class TestRouteOut(CamelModel):
    __test__ = False

    outcome: Literal["mock", "proxy", "error"]
    reason: str
    rule: MatchedRuleOut | None = None
    service: RoutedServiceOut | None = None
    upstream_url: str | None = None
    error_code: str | None = None
