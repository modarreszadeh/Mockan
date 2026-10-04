"""`/_mockan/health/live` and `/_mockan/health/ready` (G-8, PR-17)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mockan.gateway.problems import SOURCE_HEADER
from mockan.gateway.snapshot_service import SnapshotService

router = APIRouter(prefix="/_mockan/health")

# OQ-B2: health answers are Mockan-made, like a preflight, so they report `mock`.
_HEADERS = {SOURCE_HEADER: "mock", "cache-control": "no-store"}


@router.get("/live")
async def live() -> JSONResponse:
    return JSONResponse({"status": "live"}, headers=_HEADERS)


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """503 until the first snapshot loads; afterwards 200, even when `degraded`.

    A degraded Gateway keeps serving the last good rules (PR-07), so it stays in rotation.
    """
    provider = request.app.state.snapshot_provider
    service: SnapshotService | None = request.app.state.snapshot_service
    if not provider.loaded:
        return JSONResponse({"status": "starting"}, status_code=503, headers=_HEADERS)
    age = service.age_seconds if service is not None else None
    body: dict[str, object] = {
        "status": "degraded" if service is not None and service.degraded else "ready",
    }
    if age is not None:
        body["snapshotAgeSeconds"] = round(age, 1)
    return JSONResponse(body, headers=_HEADERS)
