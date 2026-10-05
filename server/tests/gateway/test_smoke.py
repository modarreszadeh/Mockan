import httpx

from mockan.gateway.app import create_app


async def test_gateway_app_boots_and_returns_404_at_root() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        response = await client.get("/")
    assert response.status_code == 404
