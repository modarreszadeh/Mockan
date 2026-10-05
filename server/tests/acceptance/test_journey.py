"""The PRD §6 journey (the Phase 1 exit scenario), scripted end to end over HTTP."""

import httpx
import pytest

from tests.acceptance.conftest import PUBLIC_BASE_URL, Stack, eventually
from tests.admin.builders import response_body

pytestmark = [pytest.mark.db, pytest.mark.req("PR-01"), pytest.mark.req("PR-07")]

DASHBOARD = "/echo/limsa/api/v1/dashboard"  # stands for `GET /limsa/api/v1/dashboard`


async def test_a_developer_mocks_one_unreleased_endpoint_and_goes_back_to_the_real_one(
    stack: Stack,
) -> None:
    # Setup by an admin: the catalog knows the upstream ("stage").
    root = await stack.sign_in("root")
    await stack.add_service(root, "echo")

    # 1-2. Ehtesham signs in (dev mode stands in for company SSO) and claims his slug; the Panel
    #      shows the base URL to put in `.env`.
    ehtesham = await stack.sign_in("ehtesham")
    me = (await ehtesham.api.get("/api/v1/me")).json()
    assert me["slug"] is None  # the onboarding screen asks for one
    await ehtesham.claim("ehtesham")
    me = (await ehtesham.api.get("/api/v1/me")).json()
    assert f"{me['publicBaseUrl']}/{me['slug']}" == f"{PUBLIC_BASE_URL}/ehtesham"

    # 3. His app starts: login and every other call are proxied to stage, unchanged.
    token = await ehtesham.call(
        "POST", "/echo/connect/token", data={"grant_type": "password", "username": "e"}
    )
    assert token.headers["x-mockan-source"] == "proxy"
    assert token.json()["method"] == "POST"
    real = await ehtesham.get(DASHBOARD)
    assert (
        real.headers["x-mockan-source"] == "proxy"
    )  # not ready on the backend side yet, still proxied

    # 4. He creates a rule for the endpoint that isn't ready, pasting the agreed JSON.
    agreed = '{"widgets":[{"id":1,"title":"Orders"}]}'
    rule = await ehtesham.rule(
        name="Dashboard", pattern=DASHBOARD, responses=[response_body(body=agreed)]
    )

    # 5. Within 2 s the app gets the mocked dashboard; every other call is still real.
    assert await ehtesham.becomes(DASHBOARD, source="mock") < 2
    mocked = await ehtesham.get(DASHBOARD)
    assert mocked.text == agreed
    assert mocked.headers["x-mockan-rule-id"] == rule["id"]
    other = await ehtesham.get("/echo/limsa/api/v1/orders/42")
    assert other.headers["x-mockan-source"] == "proxy"

    # 6. (He pushes; the frontend diff has no mock code: the base URL is the only change.)

    # 7. The backend ships the endpoint. He disables the rule; the same request is now real.
    await ehtesham.toggle(rule, False)
    assert await ehtesham.becomes(DASHBOARD, source="proxy") < 2

    # A teammate was never affected by any of it.
    carol = await stack.sign_in("carol", slug="carol")
    assert (await carol.get(DASHBOARD)).headers["x-mockan-source"] == "proxy"

    async def untouched() -> bool:
        async with httpx.AsyncClient(base_url=stack.admin.url) as anonymous:
            return (await anonymous.get("/api/v1/me")).status_code == 401

    await eventually(untouched, what="anonymous access to stay refused")
