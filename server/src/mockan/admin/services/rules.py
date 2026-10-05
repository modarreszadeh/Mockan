"""MockRules and their MockResponses (FR-05..FR-07, FR-11, PR-05, PR-06, PR-08, PR-15)."""

import hashlib
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mockan.admin.problems import DomainError, not_found, validation_error
from mockan.admin.schemas.rule import (
    ConditionIn,
    MockResponseIn,
    MockRuleCreateIn,
    MockRuleUpdateIn,
)
from mockan.admin.services.changes import diff
from mockan.domain.constants import MAX_RESPONSES_PER_RULE
from mockan.domain.enums import AuditAction, AuditEntityType, BodyMode, ConditionOperator
from mockan.domain.errors import ErrorCode
from mockan.infrastructure import audit
from mockan.infrastructure.db import notify
from mockan.infrastructure.db.errors import violated_constraint
from mockan.infrastructure.db.models import Developer, MockResponse, MockRule, Service
from mockan.matching.compile import compile_rule
from mockan.matching.errors import PatternError
from mockan.matching.model import Condition
from mockan.matching.templating import compile_template

# ---- reading ----


async def list_rules(session: AsyncSession, developer: Developer) -> list[MockRule]:
    result = await session.scalars(
        select(MockRule)
        .where(MockRule.developer_id == developer.id)
        .options(selectinload(MockRule.responses))
        .order_by(MockRule.id)  # UUIDv7: creation order
        .execution_options(populate_existing=True)
    )
    return list(result)


async def get_rule(session: AsyncSession, developer: Developer, rule_id: uuid.UUID) -> MockRule:
    """The Developer's own rule; someone else's is a 404 like a missing one (conventions §5)."""
    rule = await session.scalar(
        select(MockRule)
        .where(MockRule.id == rule_id, MockRule.developer_id == developer.id)
        .options(selectinload(MockRule.responses))
        .execution_options(populate_existing=True)
    )
    if rule is None:
        raise not_found("MockRule")
    return rule


def _find_response(rule: MockRule, response_id: uuid.UUID) -> MockResponse:
    for response in rule.responses:
        if response.id == response_id:
            return response
    raise not_found("MockResponse")


# ---- audit payloads (NFR-07: no bodies, masked headers) ----


def _conditions_json(conditions: Sequence[ConditionIn]) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    for condition in conditions:
        item: dict[str, Any] = {"key": condition.key.strip(), "operator": condition.operator.value}
        if condition.operator is ConditionOperator.EQUALS:
            item["value"] = condition.value
        stored.append(item)
    return stored


def _rule_values(rule: MockRule) -> dict[str, Any]:
    return {
        "serviceId": str(rule.service_id) if rule.service_id else None,
        "name": rule.name,
        "method": rule.method,
        "matchType": rule.match_type.value,
        "pattern": rule.pattern,
        "queryConditions": rule.query_conditions,
        "headerConditions": rule.header_conditions,
        "priority": rule.priority,
        "isEnabled": rule.is_enabled,
    }


def _response_values(response: MockResponse) -> dict[str, Any]:
    """A response without its body (it may hold secrets); size and hash show that it changed."""
    raw = response.body.encode("utf-8")
    return {
        "name": response.name,
        "statusCode": response.status_code,
        "headers": response.headers,  # masked by audit.record
        "contentType": response.content_type,
        "bodyMode": response.body_mode.value,
        "delayMs": response.delay_ms,
        "bodyBytes": len(raw),
        "bodySha256": hashlib.sha256(raw).hexdigest()[:16],
    }


# ---- validation ----


def _template_errors(responses: Sequence[MockResponseIn], prefix: str = "") -> dict[str, list[str]]:
    """Syntax errors of `Template` bodies, from the compiler the Gateway uses (PR-19)."""
    errors: dict[str, list[str]] = {}
    for index, response in enumerate(responses):
        if response.body_mode is BodyMode.TEMPLATE:
            try:
                compile_template(response.body)
            except PatternError as error:
                errors[f"{prefix}{index}.body" if prefix else "body"] = [error.message]
    return errors


async def _validate_rule(
    session: AsyncSession, data: MockRuleUpdateIn, responses: Sequence[MockResponseIn] = ()
) -> None:
    """The same compiler the Gateway runs (§2 risk), plus the Service reference and templates."""
    errors: dict[str, list[str]] = _template_errors(responses, "responses.")
    try:
        compile_rule(
            match_type=data.match_type,
            pattern=data.pattern,
            method=data.method,
            query_conditions=[Condition(c.key, c.operator, c.value) for c in data.query_conditions],
            header_conditions=[
                Condition(c.key, c.operator, c.value) for c in data.header_conditions
            ],
            priority=data.priority,
        )
    except PatternError as error:
        errors[error.field] = [error.message]
    if data.service_id and not await session.scalar(
        select(exists().where(Service.id == data.service_id))
    ):
        errors["serviceId"] = ["Unknown Service."]
    if errors:
        raise validation_error(errors)


@asynccontextmanager
async def _service_may_vanish(session: AsyncSession) -> AsyncIterator[None]:
    """A Service deleted between the check and the write is the same 422 as an unknown one."""
    try:
        yield
    except IntegrityError as error:
        await session.rollback()
        if violated_constraint(error) == "fk_mock_rules_service_id_services":
            raise validation_error({"serviceId": ["Unknown Service."]}) from error
        raise


def _touch(rule: MockRule) -> None:
    """Bump `updated_at` when only a response changed, as the Panel's list shows it."""
    rule.updated_at = func.now()  # a SQL expression, evaluated on flush


def _new_response(rule_id: uuid.UUID | None, data: MockResponseIn) -> MockResponse:
    return MockResponse(
        rule_id=rule_id,
        name=data.name,
        status_code=data.status_code,
        headers=dict(data.headers),
        content_type=data.content_type.strip() or "application/json",
        body=data.body,
        body_mode=data.body_mode,
        delay_ms=data.delay_ms,
    )


# ---- rules ----


async def create_rule(
    session: AsyncSession, developer: Developer, data: MockRuleCreateIn
) -> MockRule:
    await _validate_rule(session, data, data.responses)
    rule = MockRule(
        developer_id=developer.id,
        service_id=data.service_id,
        name=data.name,
        method=data.method,
        match_type=data.match_type,
        pattern=data.pattern,
        query_conditions=_conditions_json(data.query_conditions),
        header_conditions=_conditions_json(data.header_conditions),
        priority=data.priority,
        is_enabled=True if data.is_enabled is None else data.is_enabled,
    )
    rule.responses = [_new_response(None, response) for response in data.responses]
    async with _service_may_vanish(session):
        session.add(rule)
        await session.flush()  # inserts the rule, then its responses
        rule.active_response_id = rule.responses[0].id  # the first one is active (circular FK)
        audit.record(
            session,
            developer,
            AuditAction.CREATE,
            AuditEntityType.MOCK_RULE,
            rule.id,
            {**_rule_values(rule), "responses": [_response_values(r) for r in rule.responses]},
        )
        rule_id = rule.id
        await session.commit()
    return await get_rule(session, developer, rule_id)


async def update_rule(
    session: AsyncSession, developer: Developer, rule_id: uuid.UUID, data: MockRuleUpdateIn
) -> MockRule:
    rule = await get_rule(session, developer, rule_id)
    await _validate_rule(session, data)
    old = _rule_values(rule)
    rule.service_id = data.service_id
    rule.name = data.name
    rule.method = data.method
    rule.match_type = data.match_type
    rule.pattern = data.pattern
    rule.query_conditions = _conditions_json(data.query_conditions)
    rule.header_conditions = _conditions_json(data.header_conditions)
    rule.priority = data.priority
    if data.is_enabled is not None:
        rule.is_enabled = data.is_enabled
    changes = diff(old, _rule_values(rule))
    if not changes:
        return rule
    audit.record(
        session, developer, AuditAction.UPDATE, AuditEntityType.MOCK_RULE, rule.id, changes
    )
    async with _service_may_vanish(session):
        await session.commit()
    return await get_rule(session, developer, rule_id)


async def delete_rule(session: AsyncSession, developer: Developer, rule_id: uuid.UUID) -> None:
    rule = await get_rule(session, developer, rule_id)
    audit.record(
        session,
        developer,
        AuditAction.DELETE,
        AuditEntityType.MOCK_RULE,
        rule.id,
        _rule_values(rule),
    )
    await session.delete(rule)  # the responses go with it (ON DELETE CASCADE)
    await session.commit()


async def toggle_rule(
    session: AsyncSession, developer: Developer, rule_id: uuid.UUID, is_enabled: bool
) -> MockRule:
    """Idempotent: asking for the state the rule already has writes nothing."""
    rule = await get_rule(session, developer, rule_id)
    if rule.is_enabled == is_enabled:
        return rule
    rule.is_enabled = is_enabled
    audit.record(
        session,
        developer,
        AuditAction.TOGGLE,
        AuditEntityType.MOCK_RULE,
        rule.id,
        {"isEnabled": {"from": not is_enabled, "to": is_enabled}},
    )
    await session.commit()
    return await get_rule(session, developer, rule_id)


async def toggle_all(session: AsyncSession, developer: Developer, is_enabled: bool) -> int:
    """FR-11: one bulk UPDATE of the rules that differ; returns how many changed."""
    result = await session.execute(
        update(MockRule)
        .where(MockRule.developer_id == developer.id, MockRule.is_enabled != is_enabled)
        .values(is_enabled=is_enabled, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    updated = int(getattr(result, "rowcount", 0) or 0)
    if updated == 0:
        return 0
    notify.mark(session, developer.id)  # bulk statements skip the ORM events
    audit.record(
        session,
        developer,
        AuditAction.TOGGLE,
        AuditEntityType.MOCK_RULE,
        developer.id,
        {"scope": "all", "isEnabled": is_enabled, "updated": updated},
    )
    await session.commit()
    return updated


# ---- responses ----


async def create_response(
    session: AsyncSession, developer: Developer, rule_id: uuid.UUID, data: MockResponseIn
) -> MockResponse:
    rule = await get_rule(session, developer, rule_id)
    if errors := _template_errors([data]):
        raise validation_error(errors)
    if len(rule.responses) >= MAX_RESPONSES_PER_RULE:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            422,
            "Too many responses",
            f"A rule can have at most {MAX_RESPONSES_PER_RULE} responses.",
        )
    response = _new_response(rule.id, data)
    session.add(response)
    await session.flush()
    if rule.active_response_id is None:
        rule.active_response_id = response.id
    _touch(rule)
    audit.record(
        session,
        developer,
        AuditAction.CREATE,
        AuditEntityType.MOCK_RESPONSE,
        response.id,
        {"ruleId": str(rule.id), **_response_values(response)},
    )
    await session.commit()
    return response


async def update_response(
    session: AsyncSession,
    developer: Developer,
    rule_id: uuid.UUID,
    response_id: uuid.UUID,
    data: MockResponseIn,
) -> MockResponse:
    rule = await get_rule(session, developer, rule_id)
    response = _find_response(rule, response_id)
    if errors := _template_errors([data]):
        raise validation_error(errors)
    old = _response_values(response)
    response.name = data.name
    response.status_code = data.status_code
    response.headers = dict(data.headers)
    response.content_type = data.content_type.strip() or "application/json"
    response.body = data.body
    response.body_mode = data.body_mode
    response.delay_ms = data.delay_ms
    changes = diff(old, _response_values(response))
    if not changes:
        return response
    _touch(rule)
    audit.record(
        session,
        developer,
        AuditAction.UPDATE,
        AuditEntityType.MOCK_RESPONSE,
        response.id,
        {"ruleId": str(rule.id), **changes},
    )
    await session.commit()
    return response


async def delete_response(
    session: AsyncSession, developer: Developer, rule_id: uuid.UUID, response_id: uuid.UUID
) -> None:
    rule = await get_rule(session, developer, rule_id)
    response = _find_response(rule, response_id)
    others = [r for r in rule.responses if r.id != response_id]
    if not others:  # G-3: a rule always has an active response
        raise DomainError(
            ErrorCode.LAST_RESPONSE,
            409,
            "A rule needs at least one response",
            "Add another response first, or delete the rule.",
        )
    if rule.active_response_id == response_id:
        rule.active_response_id = others[0].id
        await session.flush()  # move the pointer before the row it points at goes away
    _touch(rule)
    audit.record(
        session,
        developer,
        AuditAction.DELETE,
        AuditEntityType.MOCK_RESPONSE,
        response.id,
        {"ruleId": str(rule.id), **_response_values(response)},
    )
    await session.delete(response)
    await session.commit()


async def activate_response(
    session: AsyncSession, developer: Developer, rule_id: uuid.UUID, response_id: uuid.UUID
) -> MockRule:
    rule = await get_rule(session, developer, rule_id)
    _find_response(rule, response_id)
    if rule.active_response_id == response_id:
        return rule
    previous = rule.active_response_id
    rule.active_response_id = response_id
    audit.record(
        session,
        developer,
        AuditAction.ACTIVATE,
        AuditEntityType.MOCK_RESPONSE,
        response_id,
        {
            "ruleId": str(rule.id),
            "activeResponseId": {
                "from": str(previous) if previous else None,
                "to": str(response_id),
            },
        },
    )
    await session.commit()
    return await get_rule(session, developer, rule_id)
