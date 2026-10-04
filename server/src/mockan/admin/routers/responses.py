"""`/me/rules/{ruleId}/responses`: a rule's MockResponses (FR-07, PR-06)."""

import uuid

from fastapi import APIRouter, Response

from mockan.admin.auth import WritableDeveloper
from mockan.admin.deps import SessionDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.rule import MockResponseIn, MockResponseOut, MockRuleOut
from mockan.admin.services import rules

router = APIRouter(prefix="/me/rules/{rule_id}/responses", tags=["responses"])


@router.post(
    "", status_code=201, response_model=MockResponseOut, responses=problems(401, 403, 404, 422)
)
async def create_response(
    rule_id: uuid.UUID, data: MockResponseIn, developer: WritableDeveloper, session: SessionDep
) -> MockResponseOut:
    """The first response of a rule becomes its active one; later ones wait to be activated."""
    return MockResponseOut.model_validate(
        await rules.create_response(session, developer, rule_id, data)
    )


@router.put(
    "/{response_id}", response_model=MockResponseOut, responses=problems(401, 403, 404, 422)
)
async def update_response(
    rule_id: uuid.UUID,
    response_id: uuid.UUID,
    data: MockResponseIn,
    developer: WritableDeveloper,
    session: SessionDep,
) -> MockResponseOut:
    return MockResponseOut.model_validate(
        await rules.update_response(session, developer, rule_id, response_id, data)
    )


@router.delete(
    "/{response_id}",
    status_code=204,
    responses={**problems(401, 403, 404), 409: problems(409)[409]},
)
async def delete_response(
    rule_id: uuid.UUID, response_id: uuid.UUID, developer: WritableDeveloper, session: SessionDep
) -> Response:
    """The last response of a rule can't be deleted (`409 last_response`, G-3)."""
    await rules.delete_response(session, developer, rule_id, response_id)
    return Response(status_code=204)


@router.post(
    "/{response_id}/activate", response_model=MockRuleOut, responses=problems(401, 403, 404)
)
async def activate_response(
    rule_id: uuid.UUID, response_id: uuid.UUID, developer: WritableDeveloper, session: SessionDep
) -> MockRuleOut:
    """Makes this response the one the Gateway serves; returns the rule."""
    return MockRuleOut.model_validate(
        await rules.activate_response(session, developer, rule_id, response_id)
    )
