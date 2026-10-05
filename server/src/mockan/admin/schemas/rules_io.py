"""Export / import of a Developer's rules (FR-12, PR-14): a versioned JSON file without ids."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt

from mockan.admin.schemas.base import CamelInput, CamelModel
from mockan.admin.schemas.rule import ConditionOut, MockResponseIn, RuleFieldsIn
from mockan.domain.constants import MAX_RESPONSES_PER_RULE
from mockan.domain.enums import BodyMode, MatchType

MAX_IMPORTED_RULES = 200


class ExportedResponse(CamelModel):
    name: str
    status_code: int
    headers: dict[str, str]
    content_type: str
    body: str
    body_mode: BodyMode
    delay_ms: int


class ExportedRule(CamelModel):
    name: str
    method: str
    match_type: MatchType
    pattern: str
    query_conditions: list[ConditionOut]
    header_conditions: list[ConditionOut]
    priority: int
    is_enabled: bool
    service_name: str | None  # a Service is named, not identified: ids differ between systems
    active_response: int  # index into `responses`
    responses: list[ExportedResponse]


class RuleExport(CamelModel):
    version: Literal[1] = 1
    rules: list[ExportedRule]


class ImportedRule(RuleFieldsIn):
    is_enabled: StrictBool = True
    service_name: str | None = None
    active_response: Annotated[StrictInt, Field(ge=0)] = 0
    responses: Annotated[
        list[MockResponseIn], Field(min_length=1, max_length=MAX_RESPONSES_PER_RULE)
    ]


class RuleImport(CamelInput):
    version: Literal[1]
    rules: Annotated[list[ImportedRule], Field(max_length=MAX_IMPORTED_RULES)]


class ImportResult(CamelModel):
    mode: Literal["merge", "replace"]
    created: int
    deleted: int
