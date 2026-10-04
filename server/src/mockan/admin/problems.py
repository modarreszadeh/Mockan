"""Exception → RFC 7807 problem+json for the Admin API (G-1, G-5, arch §14 rule 8).

Validation failures are `422` with `code: "validation_failed"` and `errors: {"<camelCase.dotted
path>": ["message", …]}`, the shape the Panel maps onto form fields (`panel/src/api/client.ts`).
"""

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mockan.domain.errors import ErrorCode
from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

PROBLEM_JSON = "application/problem+json"
_LOCATION_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})
_HTTP_STATUS_CODES = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
}


class DomainError(Exception):
    """A business-rule failure the client can act on; the handler turns it into a problem."""

    def __init__(
        self,
        code: ErrorCode,
        status: int,
        title: str,
        detail: str | None = None,
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.code = code
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors


def validation_error(errors: dict[str, list[str]]) -> DomainError:
    """A 422 carrying field errors, for rules that need the database or the settings."""
    return DomainError(
        ErrorCode.VALIDATION_FAILED, 422, "Some fields need attention", errors=errors
    )


def not_found(what: str) -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, 404, f"{what} not found")


def problem_response(
    settings: MockanSettings,
    code: ErrorCode,
    status: int,
    title: str,
    detail: str | None = None,
    errors: dict[str, list[str]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{settings.public_base_url.rstrip('/')}/problems/{code.value}",
        "title": title,
        "status": status,
        "code": code.value,
    }
    if detail is not None:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_JSON, headers={"cache-control": "no-store"}
    )


def field_errors(exc: RequestValidationError) -> dict[str, list[str]]:
    """Pydantic errors → `{camelCase.dotted.path: [message]}`.

    Locations already use the camelCase aliases because inputs validate by alias. Errors with no
    field (e.g. a body that is not JSON) are left out; the problem `detail` carries them.
    """
    result: dict[str, list[str]] = {}
    for error in exc.errors():
        loc = [part for part in error["loc"] if part not in _LOCATION_PREFIXES]
        if error["type"] == "json_invalid" or not loc or all(isinstance(p, int) for p in loc):
            continue
        message = str(error["msg"]).removeprefix("Value error, ")
        result.setdefault(".".join(str(part) for part in loc), []).append(message)
    return result


def install_problem_handlers(app: FastAPI, settings: MockanSettings) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_request: Request, exc: DomainError) -> JSONResponse:
        return problem_response(settings, exc.code, exc.status, exc.title, exc.detail, exc.errors)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        raw = exc.errors()
        if raw and all(error["loc"] and error["loc"][0] == "path" for error in raw):
            # A malformed id can't name anything: same answer as an unknown id.
            return problem_response(settings, ErrorCode.NOT_FOUND, 404, "Not found")
        errors = field_errors(exc)
        detail = (
            "The request body isn't valid JSON."
            if any(error["type"] == "json_invalid" for error in raw)
            else None
        )
        return problem_response(
            settings,
            ErrorCode.VALIDATION_FAILED,
            422,
            "Some fields need attention",
            detail,
            errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(
            exc.status_code,
            ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.VALIDATION_FAILED,
        )
        title = HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus else "Error"
        response = problem_response(settings, code, exc.status_code, title, str(exc.detail))
        for name, value in (exc.headers or {}).items():  # e.g. `Allow` on a 405
            response.headers[name] = value
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Logged through structlog, so the masking processor runs (NFR-07).
        log.error("unhandled_error", method=request.method, path=request.url.path, exc_info=exc)
        return problem_response(
            settings,
            ErrorCode.INTERNAL_ERROR,
            500,
            "Internal error",
            "Something went wrong on our side. Try again in a moment.",
        )
