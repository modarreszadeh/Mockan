"""Resolve the Developer from the first path segment (arch §6.2 step 4, FR-01, PR-01)."""

from starlette.types import ASGIApp, Receive, Scope, Send

from mockan.domain.errors import ErrorCode
from mockan.gateway.context import (
    MockanContext,
    developer_not_found_detail,
    find_developer,
    is_internal,
    set_context,
    snapshot_for,
)
from mockan.gateway.problems import problem_response
from mockan.infrastructure.logging import bind_log_context
from mockan.matching.snapshot import RuleSnapshotProvider


class DeveloperResolutionMiddleware:
    def __init__(
        self, app: ASGIApp, *, provider: RuleSnapshotProvider, public_base_url: str
    ) -> None:
        self.app = app
        self._provider = provider
        self._public_base_url = public_base_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_internal(scope):
            await self.app(scope, receive, send)
            return

        snapshot = snapshot_for(scope, self._provider)
        path: str = scope["path"]
        developer, slug, rest = find_developer(snapshot, path)

        if developer is None:
            response = problem_response(
                ErrorCode.DEVELOPER_NOT_FOUND,
                404,
                developer_not_found_detail(slug),
                public_base_url=self._public_base_url,
                developer=slug,
                path=path,
            )
            await response(scope, receive, send)
            return

        set_context(
            scope, MockanContext(snapshot=snapshot, developer=developer, path_after_slug=rest)
        )
        bind_log_context(developer=developer.slug)
        await self.app(scope, receive, send)
