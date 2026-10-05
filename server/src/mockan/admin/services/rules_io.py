"""Export and import of a Developer's rules (FR-12, PR-14).

Import validates **everything** first (the Gateway's compiler for patterns and templates, every
response limit, the Service names) and reports every problem at once as `rules.<i>.<field>`; it
then saves all or nothing in one transaction. `merge` adds the rules to the existing ones;
`replace` deletes the Developer's rules first.
"""

import uuid
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mockan.admin.problems import validation_error
from mockan.admin.schemas.rule import ConditionIn, ConditionOut
from mockan.admin.schemas.rules_io import (
    ExportedResponse,
    ExportedRule,
    ImportedRule,
    ImportResult,
    RuleExport,
    RuleImport,
)
from mockan.admin.services import rules
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure import audit
from mockan.infrastructure.db import notify
from mockan.infrastructure.db.models import Developer, MockRule, Service
from mockan.matching.compile import compile_rule
from mockan.matching.errors import PatternError
from mockan.matching.model import Condition

Mode = Literal["merge", "replace"]


async def export_rules(session: AsyncSession, developer: Developer) -> RuleExport:
    names = {row.id: row.name for row in await session.execute(select(Service.id, Service.name))}
    exported: list[ExportedRule] = []
    for rule in await rules.list_rules(session, developer):
        active = next(
            (i for i, r in enumerate(rule.responses) if r.id == rule.active_response_id), 0
        )
        exported.append(
            ExportedRule(
                name=rule.name,
                method=rule.method,
                match_type=rule.match_type,
                pattern=rule.pattern,
                query_conditions=[ConditionOut.model_validate(c) for c in rule.query_conditions],
                header_conditions=[ConditionOut.model_validate(c) for c in rule.header_conditions],
                priority=rule.priority,
                is_enabled=rule.is_enabled,
                service_name=names.get(rule.service_id) if rule.service_id else None,
                active_response=active,
                responses=[
                    ExportedResponse(
                        name=r.name,
                        status_code=r.status_code,
                        headers=r.headers,
                        content_type=r.content_type,
                        body=r.body,
                        body_mode=r.body_mode,
                        delay_ms=r.delay_ms,
                    )
                    for r in rule.responses
                ],
            )
        )
    return RuleExport(rules=exported)


def _conditions(items: list[ConditionIn]) -> list[Condition]:
    return [Condition(c.key, c.operator, c.value) for c in items]


def _validate(imported: RuleImport, service_ids: dict[str, uuid.UUID]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for index, rule in enumerate(imported.rules):
        prefix = f"rules.{index}."
        try:
            compile_rule(
                match_type=rule.match_type,
                pattern=rule.pattern,
                method=rule.method,
                query_conditions=_conditions(rule.query_conditions),
                header_conditions=_conditions(rule.header_conditions),
                priority=rule.priority,
            )
        except PatternError as error:
            errors[prefix + error.field] = [error.message]
        for key, messages in rules.template_errors(rule.responses, prefix + "responses.").items():
            errors[key] = messages
        if rule.service_name is not None and rule.service_name not in service_ids:
            errors[prefix + "serviceName"] = [f"Unknown Service “{rule.service_name}”."]
        if rule.active_response >= len(rule.responses):
            errors[prefix + "activeResponse"] = [
                f"Use a number from 0 to {len(rule.responses) - 1}: the index of a response."
            ]
    return errors


async def import_rules(
    session: AsyncSession, developer: Developer, imported: RuleImport, mode: Mode
) -> ImportResult:
    service_ids: dict[str, uuid.UUID] = {
        row.name: row.id for row in await session.execute(select(Service.name, Service.id))
    }
    if errors := _validate(imported, service_ids):
        raise validation_error(errors)

    deleted = 0
    if mode == "replace":
        result = await session.execute(
            delete(MockRule)
            .where(MockRule.developer_id == developer.id)
            .execution_options(synchronize_session=False)
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)  # responses go with them (CASCADE)
        notify.mark(session, developer.id)

    created: list[MockRule] = []
    for item in imported.rules:
        rule = _new_rule(developer, item, service_ids)
        created.append(rule)
        session.add(rule)
    await session.flush()  # inserts every rule, then every response
    for rule, item in zip(created, imported.rules, strict=True):
        rule.active_response_id = rule.responses[item.active_response].id
    audit.record(
        session,
        developer,
        AuditAction.CREATE,
        AuditEntityType.MOCK_RULE,
        developer.id,
        {
            "import": mode,
            "created": len(created),
            "deleted": deleted,
            "rules": [r.name for r in created],
        },
    )
    await session.commit()
    return ImportResult(mode=mode, created=len(created), deleted=deleted)


def _new_rule(
    developer: Developer, item: ImportedRule, service_ids: dict[str, uuid.UUID]
) -> MockRule:
    rule = MockRule(
        developer_id=developer.id,
        service_id=service_ids[item.service_name] if item.service_name else None,
        name=item.name,
        method=item.method,
        match_type=item.match_type,
        pattern=item.pattern,
        query_conditions=rules.conditions_json(item.query_conditions),
        header_conditions=rules.conditions_json(item.header_conditions),
        priority=item.priority,
        is_enabled=item.is_enabled,
    )
    rule.responses = [rules.new_response(None, response) for response in item.responses]
    return rule
