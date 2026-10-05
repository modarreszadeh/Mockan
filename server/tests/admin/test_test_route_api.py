"""`POST /me/test-route`: which rule would answer, or where it would be forwarded (FR-10, PR-13)."""

import uuid
from typing import Any

import httpx
import pytest

from tests.admin.builders import ME_RULES, create_rule, response_body
from tests.admin.conftest import AsDeveloper
from tests.admin.test_services_api import create_environment, create_service

pytestmark = [pytest.mark.db, pytest.mark.req("PR-13")]

URL = "/api/v1/me/test-route"


async def ask(client: httpx.AsyncClient, path: str, **extra: Any) -> dict[str, Any]:
    response = await client.post(URL, json={"path": path, **extra})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def catalog(client: httpx.AsyncClient, as_developer: AsDeveloper) -> None:
    """A `limsa` Service (stage + dev) registered by an admin; leaves `ehtesham` signed in."""
    admin = await as_developer("root", is_admin=True)
    service = await create_service(client, name="limsa", pathPrefix="/limsa")
    await create_environment(client, service["id"], name="stage", host="identity.stage.internal")
    await create_environment(client, service["id"], name="dev", host="limsa.dev.internal")
    assert admin
    await as_developer("ehtesham")


async def test_a_matching_rule_is_a_mock_outcome_with_the_reason(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(
        admin_client,
        pattern="/limsa/api/v1/dashboard",
        priority=7,
        responses=[response_body(name="empty", statusCode=204, delayMs=250)],
    )

    result = await ask(admin_client, "/limsa/api/v1/dashboard/")

    assert result["outcome"] == "mock"
    assert result["rule"] == {
        "id": rule["id"],
        "name": "Dashboard",
        "method": "GET",
        "matchType": "Exact",
        "pattern": "/limsa/api/v1/dashboard",
        "priority": 7,
        "activeResponse": {
            "id": rule["activeResponseId"],
            "name": "empty",
            "statusCode": 204,
            "delayMs": 250,
        },
    }
    assert "Dashboard" in result["reason"] and "priority 7" in result["reason"]
    assert result["upstreamUrl"] is None and result["errorCode"] is None


async def test_method_headers_and_query_decide_like_the_gateway(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    await create_rule(
        admin_client,
        method="POST",
        pattern="/x",
        queryConditions=[{"key": "page", "operator": "equals", "value": "2"}],
        headerConditions=[{"key": "X-Tenant", "operator": "equals", "value": "a"}],
    )
    full = {"method": "POST", "query": {"page": "2"}, "headers": {"x-tenant": "a"}}

    assert (await ask(admin_client, "/x", **full))["outcome"] == "mock"
    assert (await ask(admin_client, "/x", **{**full, "method": "post"}))["outcome"] == "mock"
    assert (await ask(admin_client, "/x", **{**full, "method": "GET"}))["errorCode"] == (
        "service_not_resolved"
    )  # no rule, and no Service in this test's catalog
    assert (await ask(admin_client, "/x", **{**full, "query": {"page": ["1", "2"]}}))[
        "outcome"
    ] == "mock"  # any value equals
    assert (await ask(admin_client, "/x", **{**full, "query": {"page": "3"}}))["outcome"] == "error"
    assert (await ask(admin_client, "/x", **{**full, "headers": {"X-TENANT": "a"}}))[
        "outcome"
    ] == "mock"  # header names are case-insensitive
    assert (await ask(admin_client, "/x", **{**full, "headers": {"x-tenant": "A"}}))[
        "outcome"
    ] == "error"  # values are not


async def test_a_disabled_rule_does_not_match(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")
    rule = await create_rule(admin_client, pattern="/x")
    await admin_client.post(f"{ME_RULES}/{rule['id']}/toggle", json={"isEnabled": False})

    assert (await ask(admin_client, "/x"))["outcome"] == "error"


async def test_an_unmatched_request_reports_the_upstream_it_would_reach(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await catalog(admin_client, as_developer)

    result = await ask(admin_client, "/limsa/api/v1/orders/42", query={"a": ["1", "2"], "b": "x y"})

    assert result["outcome"] == "proxy"
    assert (
        result["upstreamUrl"]
        == "https://identity.stage.internal/limsa/api/v1/orders/42?a=1&a=2&b=x+y"
    )
    assert result["service"]["name"] == "limsa"
    assert result["service"]["environment"] == "stage"
    assert "limsa" in result["reason"]


async def test_the_developers_environment_choice_and_strip_prefix_are_honoured(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await catalog(admin_client, as_developer)
    services = (await admin_client.get("/api/v1/services")).json()
    dev_environment = next(
        e["id"] for e in services[0]["environments"] if e["environment"] == "dev"
    )
    await admin_client.put(
        "/api/v1/me/service-settings",
        json=[{"serviceId": services[0]["id"], "serviceEnvironmentId": dev_environment}],
    )

    chosen = await ask(admin_client, "/limsa/x")
    assert chosen["upstreamUrl"] == "https://limsa.dev.internal/limsa/x"
    assert chosen["service"]["environment"] == "dev"

    root = await as_developer("root2", is_admin=True)
    await admin_client.put(
        f"/api/v1/services/{services[0]['id']}",
        json={
            "name": "limsa",
            "pathPrefix": "/limsa",
            "stripPrefix": True,
            "defaultEnvironment": "stage",
        },
    )
    assert root
    await as_developer("ehtesham2")
    stripped = await ask(admin_client, "/limsa/x/y")
    assert stripped["upstreamUrl"] == "https://identity.stage.internal/x/y"


async def test_errors_carry_the_gateways_codes(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    nothing = await ask(admin_client, "/nothing/registered")

    assert nothing["outcome"] == "error"
    assert nothing["errorCode"] == "service_not_resolved"
    assert "No Service" in nothing["reason"]
    assert nothing["rule"] is None and nothing["upstreamUrl"] is None


async def test_a_host_outside_the_allowlist_is_an_upstream_error_like_in_the_gateway(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, session_factory: Any
) -> None:
    await catalog(admin_client, as_developer)
    from sqlalchemy import update

    from mockan.infrastructure.db.models import ServiceEnvironment

    async with session_factory() as session:  # an allowlisted host that later left the allowlist
        await session.execute(
            update(ServiceEnvironment).values(base_url="https://elsewhere.example.com")
        )
        await session.commit()

    result = await ask(admin_client, "/limsa/x")

    assert (result["outcome"], result["errorCode"]) == ("error", "upstream_unreachable")
    assert "elsewhere.example.com" in result["reason"]


async def test_a_developer_without_a_slug_is_told_to_claim_one(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer(None)

    result = await ask(admin_client, "/x")

    assert (result["outcome"], result["errorCode"]) == ("error", "developer_not_found")
    assert "slug" in result["reason"]


async def test_a_disabled_workspace_can_still_ask_and_is_told_why(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham", is_enabled=False)

    result = await ask(admin_client, "/x")

    assert (result["outcome"], result["errorCode"]) == ("error", "developer_not_found")
    assert "disabled" in result["reason"]


@pytest.mark.req("PR-01")
async def test_only_my_rules_are_considered(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("alice")
    await create_rule(admin_client, pattern="/shared")
    await as_developer("bob")

    assert (await ask(admin_client, "/shared"))["outcome"] == "error"  # alice's rule isn't bob's


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"path": "no-slash"}, "path"),
        ({"path": "/x?a=1"}, "path"),
        ({"path": "/x#frag"}, "path"),
        ({"path": "/x\0"}, "path"),
        ({"path": "/" + "a" * 2048}, "path"),
        ({"path": "/x", "method": "TRACE"}, "method"),
        ({"path": "/x", "headers": {"a": 1}}, "headers.a"),
        ({"path": "/x", "query": {"a": 1}}, "query.a"),
        ({"path": "/x", "query": {f"k{i}": "v" for i in range(51)}}, "query"),
        ({"path": "/x", "extra": 1}, "extra"),
        ({}, "path"),
    ],
)
async def test_bad_requests_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, body: dict[str, Any], field: str
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.post(URL, json=body)

    assert response.status_code == 422
    assert field in response.json()["errors"]


async def test_it_needs_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.post(URL, json={"path": "/x"})).status_code == 401
    assert uuid.uuid4()
