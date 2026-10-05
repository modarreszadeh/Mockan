"""`/me/request-logs`: the Developer's recent requests and "Mock this" (PR-12, FR-09)."""

from typing import Annotated

from fastapi import APIRouter, Query

from mockan.admin.auth import CurrentDeveloper, WritableDeveloper
from mockan.admin.deps import SessionDep
from mockan.admin.problems import validation_error
from mockan.admin.schemas.problem import problems
from mockan.admin.schemas.request_log import RequestLogOut, RequestLogPage
from mockan.admin.schemas.rule import MockRuleOut
from mockan.admin.services import request_logs
from mockan.domain.enums import RequestSource

router = APIRouter(prefix="/me/request-logs", tags=["request-logs"])


@router.get("", response_model=RequestLogPage, responses=problems(401, 422))
async def list_request_logs(
    developer: CurrentDeveloper,
    session: SessionDep,
    cursor: Annotated[str | None, Query(description="`nextCursor` of the previous page.")] = None,
    source: Annotated[RequestSource | None, Query()] = None,
    path: Annotated[
        str | None, Query(max_length=500, description="Contains, case-insensitive.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=request_logs.MAX_LIMIT)] = request_logs.DEFAULT_LIMIT,
) -> RequestLogPage:
    """Newest first. Page backwards with `cursor`. Kept 7 days, at most 5,000 per Developer."""
    after: int | None = None
    if cursor is not None:
        if not cursor.isdecimal() or int(cursor) < 1:
            raise validation_error({"cursor": ["Use the nextCursor of a previous page."]})
        after = int(cursor)
    found, next_cursor = await request_logs.list_logs(
        session, developer, cursor=after, source=source, path=path, limit=limit
    )
    return RequestLogPage(
        items=[RequestLogOut.model_validate(entry) for entry in found], next_cursor=next_cursor
    )


@router.post(
    "/{log_id}/create-rule",
    status_code=201,
    response_model=MockRuleOut,
    responses=problems(401, 403, 404, 422),
)
async def create_rule_from_request(
    log_id: int, developer: WritableDeveloper, session: SessionDep
) -> MockRuleOut:
    """ "Mock this": an Exact rule that answers with what was logged (FR-09). Secrets the log
    masked as `***` are left out of the headers; a body cut at 16 KB is refused."""
    return MockRuleOut.model_validate(
        await request_logs.create_rule_from_log(session, developer, log_id)
    )
