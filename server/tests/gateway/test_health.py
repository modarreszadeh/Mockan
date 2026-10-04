"""`/_mockan/health/*` (G-8, PR-17)."""

import httpx
import pytest

from mockan.gateway.app import create_app
from mockan.matching.snapshot import RuleSnapshotProvider
from tests.gateway.conftest import ClientFactory, make_settings
from tests.support.snapshot_builder import SnapshotBuilder


class FakeService:
    def __init__(self, degraded: bool, age: float | None) -> None:
        self.degraded = degraded
        self.age_seconds = age


def _client(
    provider: RuleSnapshotProvider, service: FakeService | None = None
) -> httpx.AsyncClient:
    app = create_app(make_settings(), provider)
    app.state.snapshot_service = service
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")


@pytest.mark.req("PR-17")
async def test_live_is_always_200(gateway_client: ClientFactory) -> None:
    response = await gateway_client().get("/_mockan/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.req("PR-17")
async def test_ready_is_503_starting_until_a_snapshot_has_loaded() -> None:
    async with _client(RuleSnapshotProvider()) as client:
        response = await client.get("/_mockan/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "starting"}


@pytest.mark.req("PR-17")
async def test_ready_is_200_once_loaded(snapshot_builder: SnapshotBuilder) -> None:
    provider = RuleSnapshotProvider(snapshot_builder.build())
    async with _client(provider) as client:
        response = await client.get("/_mockan/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.req("PR-17")
async def test_ready_reports_age_and_stays_200_when_degraded(
    snapshot_builder: SnapshotBuilder,
) -> None:
    provider = RuleSnapshotProvider(snapshot_builder.build())
    async with _client(provider, FakeService(degraded=False, age=3.14159)) as client:
        healthy = await client.get("/_mockan/health/ready")
    async with _client(provider, FakeService(degraded=True, age=120.0)) as client:
        degraded = await client.get("/_mockan/health/ready")
    assert healthy.json() == {"status": "ready", "snapshotAgeSeconds": 3.1}
    assert degraded.status_code == 200  # keeps serving the last good rules, so stays in rotation
    assert degraded.json() == {"status": "degraded", "snapshotAgeSeconds": 120.0}


@pytest.mark.req("PR-17")
async def test_health_routes_skip_developer_resolution_and_cors(
    snapshot_builder: SnapshotBuilder,
) -> None:
    provider = RuleSnapshotProvider(snapshot_builder.build())
    async with _client(provider) as client:
        response = await client.get(
            "/_mockan/health/live", headers={"Origin": "http://localhost:1"}
        )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
