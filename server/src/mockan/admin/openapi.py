"""OpenAPI clean-up: FastAPI's generic 422 is replaced by our problem+json (G-1)."""

from typing import Any

from fastapi import FastAPI

_GENERIC = ("HTTPValidationError", "ValidationError")


def use_problem_422(app: FastAPI) -> None:
    """Drop the auto-added `422 HTTPValidationError` so only documented problems remain.

    Routes whose 422 is a real, documented `Problem` (declared with `problems(422)`) keep it; a
    route that only has path parameters answers a malformed id with 404, so it has no 422.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = generate()
        for operations in schema["paths"].values():
            for operation in operations.values():
                response = operation["responses"].get("422")
                body = response and response.get("content", {}).get("application/json", {})
                if body and body["schema"].get("$ref", "").endswith(_GENERIC):
                    del operation["responses"]["422"]
        for name in _GENERIC:
            schema["components"]["schemas"].pop(name, None)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]  # documented FastAPI customisation
