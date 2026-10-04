"""Admin API FastAPI app factory (routers, auth and the Panel mount arrive in B5)."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the Admin app. OpenAPI lives under `/api/v1` (arch §10)."""
    return FastAPI(
        title="Mockan Admin API",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
