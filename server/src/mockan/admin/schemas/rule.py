"""`MockRule` and `MockResponse` payloads (`/me/rules*`, FR-05..FR-07, PR-05, PR-06)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, StrictInt

from mockan.admin.schemas.base import CamelInput, CamelModel
from mockan.admin.schemas.common import check_headers, no_nul
from mockan.domain.constants import (
    DEFAULT_PRIORITY,
    FORBIDDEN_MOCK_HEADERS,
    MAX_BODY_BYTES,
    MAX_CONDITION_TEXT_LENGTH,
    MAX_CONDITIONS,
    MAX_CONTENT_TYPE_LENGTH,
    MAX_DELAY_MS,
    MAX_PATTERN_LENGTH,
    MAX_PRIORITY,
    MAX_RESPONSE_HEADERS,
    MAX_RESPONSE_NAME_LENGTH,
    MAX_RESPONSES_PER_RULE,
    MAX_RULE_NAME_LENGTH,
    MAX_STATUS,
    MIN_STATUS,
)
from mockan.domain.enums import BodyMode, ConditionOperator, MatchType

Method = Literal["ANY", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def _named(label: str, limit: int) -> AfterValidator:
    def check(value: str) -> str:
        value = no_nul(value.strip())
        if not value:
            raise ValueError(f"Name the {label}.")
        if len(value) > limit:
            raise ValueError(f"Use at most {limit} characters.")
        return value

    return AfterValidator(check)


def _text(limit: int) -> AfterValidator:
    def check(value: str) -> str:
        if len(value) > limit:
            raise ValueError(f"Use at most {limit} characters.")
        return no_nul(value)

    return AfterValidator(check)


def _body(value: str) -> str:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("Body must be valid UTF-8 text.") from None
    if size > MAX_BODY_BYTES:
        raise ValueError("Body must be at most 1 MB.")
    return no_nul(value)


def _supported_mode(value: BodyMode) -> BodyMode:
    # G-13: the DB CHECK allows all three modes; the API opens them phase by phase.
    if value is BodyMode.PROXY_AND_PATCH:
        raise ValueError("ProxyAndPatch bodies aren't available yet (Phase 3).")
    return value


def _response_headers(value: dict[str, str]) -> dict[str, str]:
    return check_headers(value, MAX_RESPONSE_HEADERS, FORBIDDEN_MOCK_HEADERS)


# ---- conditions ----


class ConditionIn(CamelInput):
    """A query or header condition. `value` is required for `equals` and ignored for `exists`."""

    key: Annotated[str, _text(MAX_CONDITION_TEXT_LENGTH)]
    operator: ConditionOperator
    value: Annotated[str, _text(MAX_CONDITION_TEXT_LENGTH)] | None = None


class ConditionOut(CamelModel):
    key: str
    operator: ConditionOperator
    # The Panel's `value?: string`: absent for `exists`, never null.
    value: str | None = Field(default=None, exclude_if=lambda value: value is None)


Conditions = Annotated[list[ConditionIn], Field(max_length=MAX_CONDITIONS)]


# ---- responses ----


class MockResponseIn(CamelInput):
    name: Annotated[str, _named("scenario", MAX_RESPONSE_NAME_LENGTH)]
    status_code: Annotated[StrictInt, Field(ge=MIN_STATUS, le=MAX_STATUS)]
    headers: Annotated[dict[str, str], AfterValidator(_response_headers)] = Field(
        default_factory=dict
    )
    content_type: Annotated[str, _text(MAX_CONTENT_TYPE_LENGTH)] = "application/json"
    body: Annotated[str, AfterValidator(_body)] = ""
    body_mode: Annotated[BodyMode, AfterValidator(_supported_mode)] = BodyMode.STATIC
    delay_ms: Annotated[StrictInt, Field(ge=0, le=MAX_DELAY_MS)] = 0


class MockResponseOut(CamelModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    name: str
    status_code: int
    headers: dict[str, str]
    content_type: str
    body: str
    body_mode: BodyMode
    delay_ms: int
    created_at: datetime
    updated_at: datetime


# ---- rules ----


class RuleFieldsIn(CamelInput):
    """The matching fields every rule input has (also the import file's)."""

    name: Annotated[str, _named("rule", MAX_RULE_NAME_LENGTH)]
    method: Method = "ANY"
    match_type: MatchType
    pattern: Annotated[str, _text(MAX_PATTERN_LENGTH)]
    query_conditions: Conditions = Field(default_factory=list)
    header_conditions: Conditions = Field(default_factory=list)
    priority: Annotated[StrictInt, Field(ge=0, le=MAX_PRIORITY)] = DEFAULT_PRIORITY


class MockRuleUpdateIn(RuleFieldsIn):
    """Body of `PUT /me/rules/{id}`: the rule's own fields (responses have their own routes).

    `isEnabled` left out keeps the current value.
    """

    service_id: uuid.UUID | None = None
    is_enabled: StrictBool | None = None


class MockRuleCreateIn(MockRuleUpdateIn):
    """Body of `POST /me/rules`. The first response becomes the active one."""

    responses: Annotated[
        list[MockResponseIn], Field(min_length=1, max_length=MAX_RESPONSES_PER_RULE)
    ]


class MockRuleOut(CamelModel):
    id: uuid.UUID
    developer_id: uuid.UUID
    service_id: uuid.UUID | None
    name: str
    method: str
    match_type: MatchType
    pattern: str
    query_conditions: list[ConditionOut]
    header_conditions: list[ConditionOut]
    priority: int
    is_enabled: bool
    active_response_id: uuid.UUID | None
    responses: list[MockResponseOut]
    created_at: datetime
    updated_at: datetime


class ToggleIn(CamelInput):
    is_enabled: StrictBool


class ToggleAllOut(CamelModel):
    updated: int
