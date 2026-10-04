"""`/me/rules`: a Developer's MockRules (PR-05, PR-08, FR-11). Every query is scoped to them."""

import uuid

from fastapi import APIRouter, Response

from mockan.admin.auth import CurrentDeveloper, WritableDeveloper
from mockan.admin.deps import SessionDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.rule import (
    MockRuleCreateIn,
    MockRuleOut,
    MockRuleUpdateIn,
    ToggleAllOut,
    ToggleIn,
)
from mockan.admin.services import rules

router = APIRouter(prefix="/me/rules", tags=["rules"])


@router.get("", response_model=list[MockRuleOut], responses=problems(401))
async def list_rules(developer: CurrentDeveloper, session: SessionDep) -> list[MockRuleOut]:
    return [MockRuleOut.model_validate(r) for r in await rules.list_rules(session, developer)]


@router.post("", status_code=201, response_model=MockRuleOut, responses=problems(401, 403, 422))
async def create_rule(
    data: MockRuleCreateIn, developer: WritableDeveloper, session: SessionDep
) -> MockRuleOut:
    return MockRuleOut.model_validate(await rules.create_rule(session, developer, data))


@router.post("/toggle-all", response_model=ToggleAllOut, responses=problems(401, 403, 422))
async def toggle_all_rules(
    data: ToggleIn, developer: WritableDeveloper, session: SessionDep
) -> ToggleAllOut:
    """Turn every rule on or off at once (FR-11). `updated` counts the rules that changed."""
    return ToggleAllOut(updated=await rules.toggle_all(session, developer, data.is_enabled))


@router.get("/{rule_id}", response_model=MockRuleOut, responses=problems(401, 404))
async def get_rule(
    rule_id: uuid.UUID, developer: CurrentDeveloper, session: SessionDep
) -> MockRuleOut:
    return MockRuleOut.model_validate(await rules.get_rule(session, developer, rule_id))


@router.put("/{rule_id}", response_model=MockRuleOut, responses=problems(401, 403, 404, 422))
async def update_rule(
    rule_id: uuid.UUID, data: MockRuleUpdateIn, developer: WritableDeveloper, session: SessionDep
) -> MockRuleOut:
    """Replaces the rule's own fields; its responses are untouched."""
    return MockRuleOut.model_validate(await rules.update_rule(session, developer, rule_id, data))


@router.delete("/{rule_id}", status_code=204, responses=problems(401, 403, 404))
async def delete_rule(
    rule_id: uuid.UUID, developer: WritableDeveloper, session: SessionDep
) -> Response:
    await rules.delete_rule(session, developer, rule_id)
    return Response(status_code=204)


@router.post(
    "/{rule_id}/toggle", response_model=MockRuleOut, responses=problems(401, 403, 404, 422)
)
async def toggle_rule(
    rule_id: uuid.UUID, data: ToggleIn, developer: WritableDeveloper, session: SessionDep
) -> MockRuleOut:
    """Idempotent: sets `isEnabled` to the given value."""
    return MockRuleOut.model_validate(
        await rules.toggle_rule(session, developer, rule_id, data.is_enabled)
    )
