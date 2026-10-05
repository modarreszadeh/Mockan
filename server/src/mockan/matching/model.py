"""Immutable, pre-compiled objects the Gateway matches against (arch §7, §9)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from jinja2 import Template

from mockan.domain.enums import BodyMode, ConditionOperator, EnvironmentName, MatchType


class PathMatcher(Protocol):
    """A compiled pattern. Returns the captured route params on a match, else `None`."""

    def match(self, path: str) -> Mapping[str, str] | None: ...


@dataclass(frozen=True, slots=True)
class Condition:
    """A query or header condition. Header keys are stored lower-cased."""

    key: str
    operator: ConditionOperator
    value: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledResponse:
    id: UUID
    name: str
    status_code: int
    headers: Mapping[str, str]
    content_type: str
    body: str
    body_bytes: bytes
    body_mode: BodyMode
    delay_ms: int
    template: Template | None = None  # compiled when `body_mode` is `Template`


type SortKey = tuple[int, int, int, datetime]


@dataclass(frozen=True, slots=True)
class CompiledRule:
    id: UUID
    developer_id: UUID
    service_id: UUID | None
    name: str
    method: str  # upper-case HTTP method or "ANY"
    match_type: MatchType
    pattern: str
    matcher: PathMatcher
    # Lower-cased text every matching path (lower-cased) must start with; "" means no pre-filter.
    literal_prefix: str
    query_conditions: tuple[Condition, ...]
    header_conditions: tuple[Condition, ...]
    priority: int
    created_at: datetime
    sort_key: SortKey  # (priority, TYPE_RANK, -len(pattern), created_at); the minimum wins (§7.2)
    responses: tuple[CompiledResponse, ...]
    active_response: CompiledResponse | None


@dataclass(frozen=True, slots=True)
class EnvironmentEntry:
    id: UUID
    environment: EnvironmentName
    base_url: str
    timeout_seconds: int
    extra_headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ServiceEntry:
    id: UUID
    name: str
    path_prefix: str  # as stored, e.g. "/limsa"
    strip_prefix: bool
    rewrite_origin: bool
    default_environment: EnvironmentName
    environments: Mapping[EnvironmentName, EnvironmentEntry]


@dataclass(frozen=True, slots=True)
class DeveloperEntry:
    id: UUID
    slug: str
    display_name: str
    allowed_origins: tuple[str, ...]
    is_enabled: bool
    # service id -> chosen service_environment id. A missing Service uses its default (FR-04).
    service_environment_ids: Mapping[UUID, UUID]


@dataclass(frozen=True, slots=True)
class RequestFacts:
    """What matching needs from a request (no body). Method upper-case, header names lower-case."""

    method: str
    path: str
    query: Mapping[str, Sequence[str]]
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class MatchResult:
    rule: CompiledRule
    params: Mapping[str, str]
    reason: str
