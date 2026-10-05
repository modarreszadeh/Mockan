"""`/me/rules/export` and `/me/rules/import`: share a mock set as a JSON file (FR-12, PR-14)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from mockan.admin.auth import CurrentDeveloper, WritableDeveloper
from mockan.admin.deps import SessionDep
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.rules_io import ImportResult, RuleExport, RuleImport
from mockan.admin.services import rules_io

router = APIRouter(prefix="/me/rules", tags=["rules"])


@router.get(
    "/export",
    response_model=RuleExport,
    responses=problems(401),
)
async def export_rules(developer: CurrentDeveloper, session: SessionDep) -> RuleExport:
    """Every rule of yours with its responses, no ids: `{version: 1, rules: [...]}`.

    Services are named (`serviceName`), not identified. Headers and bodies are exported as stored:
    **they may contain secrets you put there**, so look before you share the file.
    """
    return await rules_io.export_rules(session, developer)


@router.post("/import", response_model=ImportResult, responses=problems(401, 403, 422))
async def import_rules(
    data: RuleImport,
    developer: WritableDeveloper,
    session: SessionDep,
    mode: Annotated[
        Literal["merge", "replace"], Query(description="Add to, or replace, your rules.")
    ] = "merge",
) -> ImportResult:
    """All or nothing. Everything is validated first; every problem is reported at once as
    `rules.<index>.<field>`. `merge` (default) adds the rules to yours (importing a file twice
    duplicates them); `replace` deletes your current rules first."""
    return await rules_io.import_rules(session, developer, data, mode)
