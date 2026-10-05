"""Test route (FR-10, PR-13): what the Gateway would do with a request, without sending one.

It runs the Gateway's own decision code on the Developer's slice of the snapshot, loaded the way
the Gateway loads it (`load_developer`), so the answer can't drift from what is served:
`match_request` for rules, `resolve_service` for the Service and environment, the shared upstream
URL builder, and the same allowlist check.
"""

from urllib.parse import urlencode, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from mockan.admin.schemas.test_route import (
    MatchedResponseOut,
    MatchedRuleOut,
    RoutedServiceOut,
    TestRouteIn,
    TestRouteOut,
)
from mockan.domain.errors import ErrorCode
from mockan.domain.validation import host_is_allowed
from mockan.infrastructure.db.models import Developer
from mockan.infrastructure.settings import MockanSettings
from mockan.infrastructure.snapshot_loader import load_developer, load_services
from mockan.matching.errors import ServiceNotResolvedError
from mockan.matching.matcher import match_request
from mockan.matching.model import RequestFacts
from mockan.matching.service_resolver import resolve_service
from mockan.matching.snapshot import RuleSnapshot
from mockan.matching.upstream import build_upstream_path, build_upstream_url


def _error(code: ErrorCode, reason: str) -> TestRouteOut:
    return TestRouteOut(outcome="error", reason=reason, error_code=code.value)


async def test_route(
    session: AsyncSession, settings: MockanSettings, developer: Developer, data: TestRouteIn
) -> TestRouteOut:
    loaded = await load_developer(session, developer.id)
    if loaded.developer is None:
        return _error(
            ErrorCode.DEVELOPER_NOT_FOUND,
            "You have no slug yet, so the Gateway has no address for you. Claim one first.",
        )
    if not loaded.developer.is_enabled:
        return _error(ErrorCode.DEVELOPER_NOT_FOUND, "Your workspace is disabled.")
    snapshot = RuleSnapshot.build(
        developers=[loaded.developer], rules=loaded.rules, services=await load_services(session)
    )

    query = data.query
    facts = RequestFacts(
        method=data.method,
        path=data.path,
        query=query,
        headers={name.lower(): value for name, value in data.headers.items()},
    )
    matched = match_request(snapshot.rules_for(developer.id), facts)
    # A rule without an active response is proxied by the Gateway (it has nothing to answer with).
    if matched is not None and matched.rule.active_response is not None:
        rule, response = matched.rule, matched.rule.active_response
        return TestRouteOut(
            outcome="mock",
            reason=matched.reason,
            rule=MatchedRuleOut(
                id=rule.id,
                name=rule.name,
                method=rule.method,
                match_type=rule.match_type,
                pattern=rule.pattern,
                priority=rule.priority,
                active_response=MatchedResponseOut(
                    id=response.id,
                    name=response.name,
                    status_code=response.status_code,
                    delay_ms=response.delay_ms,
                ),
            ),
        )

    try:
        resolved = resolve_service(snapshot, loaded.developer, data.path)
    except ServiceNotResolvedError as error:
        return _error(ErrorCode.SERVICE_NOT_RESOLVED, error.detail)
    service, environment = resolved.service, resolved.environment
    upstream_path = build_upstream_path(
        raw_path=None,
        upstream_path=resolved.upstream_path,
        service_prefix=service.path_prefix,
        strip_prefix=service.strip_prefix,
    )
    url = build_upstream_url(environment.base_url, upstream_path, urlencode(query, doseq=True))
    host = urlsplit(url).hostname or ""
    if not host_is_allowed(host, settings.allowed_upstream_hosts):
        return _error(
            ErrorCode.UPSTREAM_UNREACHABLE,
            f"Destination host '{host}' is not allowed by MOCKAN_ALLOWED_UPSTREAM_HOSTS.",
        )
    return TestRouteOut(
        outcome="proxy",
        reason=(
            f"No enabled rule matches; Service “{service.name}” "
            f"({service.path_prefix}) forwards to its {environment.environment.value} environment."
        ),
        service=RoutedServiceOut(
            id=service.id, name=service.name, environment=environment.environment.value
        ),
        upstream_url=url,
    )
