"""Reading a Developer's request log and turning an entry into a rule (FR-09, PR-12)."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mockan.admin.problems import DomainError, not_found, validation_error
from mockan.admin.schemas.rule import MockResponseIn, MockRuleCreateIn
from mockan.admin.services import rules
from mockan.domain.constants import FORBIDDEN_MOCK_HEADERS, HTTP_METHODS, SAMPLE_BYTES
from mockan.domain.enums import MatchType, RequestSource
from mockan.domain.errors import ErrorCode
from mockan.infrastructure.db.models import Developer, MockRule, RequestLog
from mockan.infrastructure.masking import MASK

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Response headers that describe the transfer or the upstream, not the mock.
_SKIPPED_HEADERS = frozenset({"date", "server", "set-cookie", "content-encoding", "vary", "etag"})


async def list_logs(
    session: AsyncSession,
    developer: Developer,
    *,
    cursor: int | None,
    source: RequestSource | None,
    path: str | None,
    limit: int,
) -> tuple[list[RequestLog], str | None]:
    """Newest first, keyset-paged on the id. Returns the page and the next cursor."""
    query = select(RequestLog).where(RequestLog.developer_id == developer.id)
    if cursor is not None:
        query = query.where(RequestLog.id < cursor)
    if source is not None:
        query = query.where(RequestLog.source == source)
    if path:
        query = query.where(RequestLog.path.icontains(path, autoescape=True))
    result = await session.scalars(query.order_by(RequestLog.id.desc()).limit(limit + 1))
    found = list(result)
    page = found[:limit]
    return page, str(page[-1].id) if len(found) > limit else None


async def get_log(session: AsyncSession, developer: Developer, log_id: int) -> RequestLog:
    entry = await session.scalar(
        select(RequestLog).where(RequestLog.id == log_id, RequestLog.developer_id == developer.id)
    )
    if entry is None:
        raise not_found("RequestLogEntry")
    return entry


def _mock_headers(logged: dict[str, str]) -> dict[str, str]:
    kept: dict[str, str] = {}
    for name, value in logged.items():
        lowered = name.lower()
        if (
            lowered in FORBIDDEN_MOCK_HEADERS
            or lowered in _SKIPPED_HEADERS
            or lowered.startswith(("x-mockan-", "access-control-"))
            or value == MASK  # a masked secret can't be replayed
        ):
            continue
        kept[name] = value
    return kept


async def create_rule_from_log(
    session: AsyncSession, developer: Developer, log_id: int
) -> MockRule:
    """ "Mock this" (FR-09): an Exact rule for the logged method and path, answering with the logged
    status, content type, headers and body."""
    entry = await get_log(session, developer, log_id)
    body = entry.response_body_sample or ""
    if len(body.encode("utf-8")) >= SAMPLE_BYTES:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            422,
            "The logged response is too large",
            "Only the first 16 KB of the response body were logged, so the mock would be cut off. "
            "Create the rule by hand.",
        )
    method = entry.method if entry.method in HTTP_METHODS else "ANY"
    content_type = entry.response_headers.get("content-type", "application/json")
    scenario: dict[str, Any] = {
        "name": f"Logged {entry.status_code}",
        "statusCode": entry.status_code,
        "headers": _mock_headers(entry.response_headers),
        "contentType": content_type,
        "body": body,
    }
    try:
        data = MockRuleCreateIn.model_validate(
            {
                "name": f"{method} {entry.path}"[:200],
                "method": method,
                "matchType": MatchType.EXACT,
                "pattern": entry.path,
                "responses": [MockResponseIn.model_validate(scenario).model_dump(by_alias=True)],
            }
        )
    except ValidationError as error:
        raise validation_error(
            {".".join(str(p) for p in e["loc"]): [str(e["msg"])] for e in error.errors()}
        ) from error
    return await rules.create_rule(session, developer, data)
