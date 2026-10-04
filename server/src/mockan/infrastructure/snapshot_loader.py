"""Turn database rows into the immutable, pre-compiled snapshot the Gateway matches against."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mockan.domain.enums import ConditionOperator
from mockan.infrastructure.db.models import Developer, MockRule, Service
from mockan.matching.compile import compile_response, compile_rule
from mockan.matching.errors import PatternError
from mockan.matching.model import (
    CompiledRule,
    Condition,
    DeveloperEntry,
    EnvironmentEntry,
    ServiceEntry,
)
from mockan.matching.snapshot import RuleSnapshot

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class DeveloperSlice:
    """One Developer's part of a snapshot. `developer=None`: not addressable (unknown/no slug)."""

    developer: DeveloperEntry | None
    rules: tuple[CompiledRule, ...]


def _service_entry(row: Service) -> ServiceEntry:
    environments = {
        env.environment: EnvironmentEntry(
            id=env.id,
            environment=env.environment,
            base_url=env.base_url,
            timeout_seconds=env.timeout_seconds,
            extra_headers=dict(env.extra_headers),
        )
        for env in row.environments
    }
    return ServiceEntry(
        id=row.id,
        name=row.name,
        path_prefix=row.path_prefix,
        strip_prefix=row.strip_prefix,
        rewrite_origin=row.rewrite_origin,
        default_environment=row.default_environment,
        environments=environments,
    )


def _developer_entry(row: Developer) -> DeveloperEntry | None:
    if row.slug is None:
        return None
    return DeveloperEntry(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        allowed_origins=tuple(row.allowed_origins),
        is_enabled=row.is_enabled,
        service_environment_ids={
            s.service_id: s.service_environment_id for s in row.service_settings
        },
    )


def _conditions(raw: Sequence[dict[str, Any]]) -> list[Condition]:
    return [
        Condition(item["key"], ConditionOperator(item["operator"]), item.get("value"))
        for item in raw
    ]


def _compile_row(row: MockRule) -> CompiledRule | None:
    """Compile one rule row. A rule that can't be compiled is skipped and logged: the Admin
    validates on save, so this only happens after a bad manual edit of the database."""
    try:
        responses = [
            compile_response(
                response_id=r.id,
                name=r.name,
                status_code=r.status_code,
                headers=r.headers,
                content_type=r.content_type,
                body=r.body,
                body_mode=r.body_mode,
                delay_ms=r.delay_ms,
            )
            for r in row.responses
        ]
        rule = compile_rule(
            match_type=row.match_type,
            pattern=row.pattern,
            method=row.method,
            query_conditions=_conditions(row.query_conditions),
            header_conditions=_conditions(row.header_conditions),
            priority=row.priority,
            rule_id=row.id,
            developer_id=row.developer_id,
            service_id=row.service_id,
            name=row.name,
            created_at=row.created_at,
            responses=responses,
            active_response_id=row.active_response_id,
        )
    except (PatternError, KeyError, TypeError, ValueError) as error:
        log.warning(
            "rule_skipped",
            rule_id=str(row.id),
            developer_id=str(row.developer_id),
            reason=str(error),
        )
        return None
    if rule.active_response is None:
        log.warning(
            "rule_skipped",
            rule_id=str(row.id),
            developer_id=str(row.developer_id),
            reason="no active response",
        )
        return None
    return rule


def _rule_query() -> Any:
    return (
        select(MockRule)
        .join(Developer, Developer.id == MockRule.developer_id)
        .where(MockRule.is_enabled, Developer.is_enabled, Developer.slug.is_not(None))
        .options(selectinload(MockRule.responses))
    )


async def load_services(session: AsyncSession) -> tuple[ServiceEntry, ...]:
    rows = await session.scalars(select(Service).options(selectinload(Service.environments)))
    return tuple(_service_entry(row) for row in rows)


async def load_full(session: AsyncSession) -> RuleSnapshot:
    """The whole snapshot: every addressable Developer, every enabled rule, the Service catalog."""
    services = await load_services(session)
    developer_rows = await session.scalars(
        select(Developer)
        .where(Developer.slug.is_not(None))
        .options(selectinload(Developer.service_settings))
    )
    developers = [entry for row in developer_rows if (entry := _developer_entry(row))]
    rule_rows = await session.scalars(_rule_query())
    rules = [rule for row in rule_rows if (rule := _compile_row(row))]
    return RuleSnapshot.build(developers=developers, rules=rules, services=services)


async def load_developer(session: AsyncSession, developer_id: uuid.UUID) -> DeveloperSlice:
    """Rebuild one Developer's slice (a cheap partial reload; also used by test-route)."""
    row = await session.scalar(
        select(Developer)
        .where(Developer.id == developer_id)
        .options(selectinload(Developer.service_settings))
        .execution_options(populate_existing=True)
    )
    entry = _developer_entry(row) if row is not None else None
    if entry is None or not entry.is_enabled:
        return DeveloperSlice(entry, ())
    rule_rows = await session.scalars(
        _rule_query()
        .where(MockRule.developer_id == developer_id)
        .execution_options(populate_existing=True)
    )
    return DeveloperSlice(entry, tuple(rule for row in rule_rows if (rule := _compile_row(row))))
