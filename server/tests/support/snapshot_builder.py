"""Fluent in-memory `RuleSnapshot` builder for matching and Gateway tests (no database)."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mockan.domain.enums import BodyMode, ConditionOperator, EnvironmentName, MatchType
from mockan.matching.compile import compile_response, compile_rule
from mockan.matching.model import (
    CompiledRule,
    Condition,
    DeveloperEntry,
    EnvironmentEntry,
    RequestFacts,
    ServiceEntry,
)
from mockan.matching.snapshot import RuleSnapshot

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def facts(
    path: str,
    method: str = "GET",
    query: Mapping[str, Sequence[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> RequestFacts:
    return RequestFacts(
        method=method,
        path=path,
        query=query or {},
        headers={name.lower(): value for name, value in (headers or {}).items()},
    )


def equals(key: str, value: str) -> Condition:
    return Condition(key, ConditionOperator.EQUALS, value)


def exists(key: str) -> Condition:
    return Condition(key, ConditionOperator.EXISTS)


class SnapshotBuilder:
    def __init__(self) -> None:
        self._developers: list[DeveloperEntry] = []
        self._rules: list[CompiledRule] = []
        self._services: list[ServiceEntry] = []
        self._tick = 0

    def developer(
        self,
        slug: str,
        *,
        is_enabled: bool = True,
        origins: Sequence[str] = ("http://localhost:*",),
        environment_ids: Mapping[UUID, UUID] | None = None,
    ) -> DeveloperEntry:
        entry = DeveloperEntry(
            id=uuid.uuid7(),
            slug=slug,
            display_name=slug.title(),
            allowed_origins=tuple(origins),
            is_enabled=is_enabled,
            service_environment_ids=dict(environment_ids or {}),
        )
        self._developers.append(entry)
        return entry

    def service(
        self,
        name: str,
        path_prefix: str,
        *,
        strip_prefix: bool = False,
        default_environment: EnvironmentName = EnvironmentName.STAGE,
        environments: Mapping[EnvironmentName, str] | None = None,
    ) -> ServiceEntry:
        urls = environments or {
            EnvironmentName.DEV: f"https://{name}.dev.internal",
            EnvironmentName.STAGE: f"https://{name}.stage.internal",
        }
        entry = ServiceEntry(
            id=uuid.uuid7(),
            name=name,
            path_prefix=path_prefix,
            strip_prefix=strip_prefix,
            rewrite_origin=False,
            default_environment=default_environment,
            environments={
                env: EnvironmentEntry(uuid.uuid7(), env, url, 100, {}) for env, url in urls.items()
            },
        )
        self._services.append(entry)
        return entry

    def rule(
        self,
        developer: DeveloperEntry,
        match_type: MatchType,
        pattern: str,
        *,
        name: str | None = None,
        method: str = "ANY",
        priority: int = 100,
        query: Sequence[Condition] = (),
        headers: Sequence[Condition] = (),
        status: int = 200,
        body: str = "{}",
        response_headers: Mapping[str, str] | None = None,
        content_type: str = "application/json",
        delay_ms: int = 0,
        created_at: datetime | None = None,
    ) -> CompiledRule:
        self._tick += 1
        response = compile_response(
            response_id=uuid.uuid7(),
            name="default",
            status_code=status,
            headers=response_headers or {},
            content_type=content_type,
            body=body,
            body_mode=BodyMode.STATIC,
            delay_ms=delay_ms,
        )
        rule = compile_rule(
            match_type=match_type,
            pattern=pattern,
            method=method,
            priority=priority,
            query_conditions=query,
            header_conditions=headers,
            rule_id=uuid.uuid7(),
            developer_id=developer.id,
            name=name or f"rule-{self._tick}",
            created_at=created_at or BASE_TIME + timedelta(seconds=self._tick),
            responses=[response],
            active_response_id=response.id,
        )
        self._rules.append(rule)
        return rule

    def build(self) -> RuleSnapshot:
        return RuleSnapshot.build(
            developers=self._developers, rules=self._rules, services=self._services
        )
