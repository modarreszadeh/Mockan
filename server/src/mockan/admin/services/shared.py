"""Read a MockRule through its public share link (S-3, S-4). No Developer is signed in."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mockan.admin.problems import not_found
from mockan.admin.schemas.rule import ConditionOut, MockResponseOut
from mockan.admin.schemas.shared import SharedOwnerOut, SharedRuleOut, SharedServiceOut
from mockan.infrastructure.db.models import Developer, MockRule, Service


async def get_shared_rule(session: AsyncSession, token: str, public_base_url: str) -> SharedRuleOut:
    """The rule's live state. Unknown or revoked tokens and disabled owners are all a 404."""
    row = (
        await session.execute(
            select(MockRule, Developer)
            .join(Developer, Developer.id == MockRule.developer_id)
            .where(MockRule.share_token == token)
            .options(selectinload(MockRule.responses))
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None or not row.Developer.is_enabled:
        raise not_found("Shared rule")
    rule, owner = row.MockRule, row.Developer
    service = await session.get(Service, rule.service_id) if rule.service_id is not None else None
    return SharedRuleOut(
        name=rule.name,
        method=rule.method,
        match_type=rule.match_type,
        pattern=rule.pattern,
        query_conditions=[ConditionOut.model_validate(c) for c in rule.query_conditions],
        header_conditions=[ConditionOut.model_validate(c) for c in rule.header_conditions],
        priority=rule.priority,
        is_enabled=rule.is_enabled,
        active_response_id=rule.active_response_id,
        responses=[MockResponseOut.model_validate(r) for r in rule.responses],
        service=(
            SharedServiceOut(name=service.name, path_prefix=service.path_prefix)
            if service is not None
            else None
        ),
        owner=SharedOwnerOut(display_name=owner.display_name, slug=owner.slug),
        public_base_url=public_base_url,
        updated_at=rule.updated_at,
    )
