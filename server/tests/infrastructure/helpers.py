"""Small builders for rows used by the database tests."""

import uuid
from typing import Any

from mockan.domain.enums import EnvironmentName, MatchType
from mockan.infrastructure.db.models import (
    Developer,
    MockResponse,
    MockRule,
    Service,
    ServiceEnvironment,
)


def make_developer(slug: str | None = "ehtesham", **overrides: Any) -> Developer:
    values: dict[str, Any] = {
        "slug": slug,
        "display_name": (slug or "new").title(),
        "sso_subject": f"sso|{uuid.uuid4()}",
        "allowed_origins": ["http://localhost:*"],
    }
    return Developer(**{**values, **overrides})


def make_service(name: str = "limsa", prefix: str = "/limsa") -> Service:
    service = Service(name=name, path_prefix=prefix)
    service.environments = [
        ServiceEnvironment(environment=env, base_url=f"https://{name}.{env.value}.internal")
        for env in EnvironmentName
    ]
    return service


def make_rule(
    developer: Developer,
    pattern: str = "/limsa/api/v1/dashboard",
    *,
    match_type: MatchType = MatchType.EXACT,
    **overrides: Any,
) -> tuple[MockRule, MockResponse]:
    """A rule plus its single response. Persist with `add_rule` (two-step: the FK is circular)."""
    rule = MockRule(
        developer_id=developer.id,
        name=f"rule {pattern}",
        match_type=match_type,
        pattern=pattern,
        **overrides,
    )
    response = MockResponse(
        rule_id=rule.id, name="success", status_code=200, headers={"X-A": "1"}, body='{"ok":true}'
    )
    return rule, response
