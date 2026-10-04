"""Gateway FastAPI app factory (the real pipeline arrives in B3)."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the Gateway app. The first path segment is a DeveloperSlug, so no docs routes."""
    return FastAPI(title="Mockan Gateway", docs_url=None, redoc_url=None, openapi_url=None)
