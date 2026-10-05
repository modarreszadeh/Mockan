"""`RequestLogEntry` and its page (`GET /me/request-logs`, the live hub; PR-12)."""

import uuid
from datetime import datetime

from mockan.admin.schemas.base import CamelModel
from mockan.domain.enums import RequestSource


class RequestLogOut(CamelModel):
    """Headers and bodies arrive already masked (NFR-07); never unmask them."""

    id: int
    developer_id: uuid.UUID
    timestamp: datetime
    method: str
    path: str
    query: str
    service_id: uuid.UUID | None
    source: RequestSource
    rule_id: uuid.UUID | None
    status_code: int
    duration_ms: int
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    request_body_sample: str | None
    response_body_sample: str | None


class RequestLogPage(CamelModel):
    items: list[RequestLogOut]
    next_cursor: str | None  # pass it back as `cursor` for the next (older) page
