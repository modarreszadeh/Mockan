"""Resolve the Developer from the first path segment (arch §6.2 step 4, FR-01, PR-01)."""

from starlette.types import ASGIApp, Receive, Scope, Send

from mockan.domain.errors import ErrorCode
from mockan.domain.validation import is_reserved_slug
from mockan.gateway.context import (
    MockanContext,
    is_internal,
    set_context,
    snapshot_for,
    split_slug,
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
        slug, rest = split_slug(path)
        developer = None
        if slug and not is_reserved_slug(slug):
            developer = snapshot.developer_for_slug(slug)

        if developer is None or not developer.is_enabled:
            detail = (
                f"No enabled Developer with slug '{slug}'."
                if slug
                else "The request path has no Developer slug; use /{developerSlug}/..."
            )
            response = problem_response(
                ErrorCode.DEVELOPER_NOT_FOUND,
                404,
                detail,
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
