"""Request bodies and small helpers shared by the rule and response tests."""

from typing import Any

import httpx

ME_RULES = "/api/v1/me/rules"


def response_body(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "success",
        "statusCode": 200,
        "headers": {"X-A": "1"},
        "contentType": "application/json",
        "body": '{"ok":true}',
        "delayMs": 0,
        **overrides,
    }


def rule_body(**overrides: Any) -> dict[str, Any]:
    return {
        "serviceId": None,
        "name": "Dashboard",
        "method": "GET",
        "matchType": "Exact",
        "pattern": "/limsa/api/v1/dashboard",
        "queryConditions": [],
        "headerConditions": [],
        "priority": 100,
        "responses": [response_body()],
        **overrides,
    }


async def create_rule(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(ME_RULES, json=rule_body(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def update_body(rule: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A PUT body from a rule as the API returned it (no responses, no ids)."""
    keep = (
        "serviceId",
        "name",
        "method",
        "matchType",
        "pattern",
        "queryConditions",
        "headerConditions",
        "priority",
    )
    return {**{key: rule[key] for key in keep}, **overrides}
