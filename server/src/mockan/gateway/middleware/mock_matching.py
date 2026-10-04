"""Answer with the winning MockRule's active response instead of proxying (FR-05, FR-06, PR-06)."""

import asyncio
from collections.abc import Mapping
from urllib.parse import parse_qs

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mockan.domain.constants import FORBIDDEN_MOCK_HEADERS
from mockan.domain.enums import RequestSource
from mockan.gateway.context import MockanContext, get_context, is_internal
from mockan.gateway.problems import RULE_ID_HEADER, SOURCE_HEADER
from mockan.matching.matcher import match_request
from mockan.matching.model import CompiledResponse, CompiledRule, RequestFacts

_BODYLESS = frozenset({204, 304}) | frozenset(range(100, 200))


class MockMatchingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        context = get_context(scope) if scope["type"] == "http" and not is_internal(scope) else None
        if context is None:
            await self.app(scope, receive, send)
            return

        result = match_request(
            context.snapshot.rules_for(context.developer.id), _facts(scope, context)
        )
        if result is None or result.rule.active_response is None:
            await self.app(scope, receive, send)  # no rule: proxy
            return

        rule, active = result.rule, result.rule.active_response
        context.source = RequestSource.MOCKED
        context.rule_id = rule.id
        if active.delay_ms:
            await asyncio.sleep(active.delay_ms / 1000)  # never time.sleep (arch §14 rule 10)
        await _mock_response(rule, active)(scope, receive, send)


def _facts(scope: Scope, context: MockanContext) -> RequestFacts:
    headers: dict[str, str] = {}
    for name, value in scope["headers"]:
        key = name.decode("latin-1").lower()
        text = value.decode("latin-1")
        headers[key] = f"{headers[key]}, {text}" if key in headers else text
    query = parse_qs(scope["query_string"].decode("latin-1"), keep_blank_values=True)
    return RequestFacts(
        method=scope["method"], path=context.path_after_slug, query=query, headers=headers
    )


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.strip().lower()
        if not lowered or lowered in FORBIDDEN_MOCK_HEADERS:
            continue
        if any(ch in text for text in (name, value) for ch in "\r\n\0"):
            continue  # header injection (defence in depth; the Admin rejects these on save)
        safe[lowered] = value
    return safe


def _mock_response(rule: CompiledRule, response: CompiledResponse) -> Response:
    headers = _safe_headers(response.headers)
    headers["content-type"] = response.content_type
    headers[SOURCE_HEADER] = "mock"
    headers[RULE_ID_HEADER] = str(rule.id)
    body = b"" if response.status_code in _BODYLESS else response.body_bytes
    return Response(content=body, status_code=response.status_code, headers=headers)
