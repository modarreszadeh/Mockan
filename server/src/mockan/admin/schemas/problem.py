"""The problem+json body, for OpenAPI (the handlers in `admin/problems.py` build the real thing)."""

from typing import Any

from pydantic import BaseModel


class Problem(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: dict[str, list[str]] | None = None


_DESCRIPTIONS = {
    401: "Not signed in (`unauthenticated`).",
    403: "`forbidden` (not an admin) or `developer_disabled`.",
    404: "`not_found`: unknown, or someone else's.",
    409: "A conflict; `code` says which (`slug_taken`, `name_taken`, ...).",
    422: "`validation_failed` (or `upstream_host_not_allowed`) with field `errors`.",
}


def problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """The `responses=` entry that documents these statuses as problem+json."""
    return {status: {"model": Problem, "description": _DESCRIPTIONS[status]} for status in statuses}
