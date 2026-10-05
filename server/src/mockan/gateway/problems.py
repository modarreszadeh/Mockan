"""RFC 7807 problem+json responses (arch §14 rule 8, PR-16). Always `X-Mockan-Source: error`."""

import json
from typing import Any

from starlette.responses import Response

from mockan.domain.errors import ErrorCode

SOURCE_HEADER = "x-mockan-source"
RULE_ID_HEADER = "x-mockan-rule-id"

_TITLES: dict[ErrorCode, str] = {
    ErrorCode.DEVELOPER_NOT_FOUND: "Developer not found",
    ErrorCode.SERVICE_NOT_RESOLVED: "Service not resolved",
    ErrorCode.UPSTREAM_UNREACHABLE: "Upstream unreachable",
    ErrorCode.UPSTREAM_TIMEOUT: "Upstream timed out",
    ErrorCode.MOCK_RENDER_FAILED: "Mock response could not be rendered",
    ErrorCode.INTERNAL_ERROR: "Internal error",
}


def problem_response(
    code: ErrorCode,
    status: int,
    detail: str,
    *,
    public_base_url: str,
    developer: str | None = None,
    path: str | None = None,
) -> Response:
    """Build a Mockan problem response carrying the slug and path (PR-16)."""
    body: dict[str, Any] = {
        "type": f"{public_base_url.rstrip('/')}/problems/{code.value}",
        "title": _TITLES.get(code, code.value.replace("_", " ").capitalize()),
        "status": status,
        "code": code.value,
        "detail": detail,
    }
    if developer is not None:
        body["developer"] = developer
    if path is not None:
        body["path"] = path
    return Response(
        content=json.dumps(body),
        status_code=status,
        media_type="application/problem+json",
        headers={SOURCE_HEADER: "error", "cache-control": "no-store"},
    )
