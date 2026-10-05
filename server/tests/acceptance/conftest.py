"""The Phase 1 stack for acceptance tests: real Admin, real Gateway, real upstream, one PostgreSQL.

Every service listens on a real socket and is driven over HTTP only; configuration is made through
the Admin API exactly as the Panel does. Nothing is mocked.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mockan.admin.app import create_app as create_admin
from mockan.gateway.app import create_app as create_gateway
from mockan.infrastructure.settings import MockanSettings
from tests.admin.builders import ME_RULES, response_body, rule_body
from tests.support.fake_upstream import UpstreamState, build_fake_upstream
from tests.support.live_server import LiveServer

PUBLIC_BASE_URL = "https://mock.test"
TWO_SECONDS = 2.0

# One Service per route of the fake upstream, each with the same path prefix as the route.
UPSTREAM_ROUTES = (
    "echo",
    "download",
    "redirect",
    "set-cookie",
    "cors",
    "slow",
    "created",
    "status",
    "stream",
)


@dataclass
class Upstream:
    server: LiveServer
    state: UpstreamState

    @property
    def url(self) -> str:
        return self.server.url


@dataclass
class Person:
    """A signed-in user of the Admin API, with the Gateway address of their workspace."""

    stack: Stack
    api: httpx.AsyncClient
    slug: str | None = None

    async def put(self, path: str, body: Any, expect: int = 200) -> httpx.Response:
        response = await self.api.put(f"/api/v1{path}", json=body)
        assert response.status_code == expect, response.text
        return response

    async def post(self, path: str, body: Any = None, expect: int = 200) -> httpx.Response:
        response = await self.api.post(f"/api/v1{path}", json=body)
        assert response.status_code == expect, response.text
        return response

    async def claim(self, slug: str) -> None:
        """Claim the slug; returns once the Gateway answers at the new address (within 2 s)."""
        await self.put("/me", {"slug": slug})
        self.slug = slug

        async def known() -> bool:
            response = await self.stack.gateway_client.get(f"/{slug}/probe")
            return response.status_code != 404 or response.json()["code"] != "developer_not_found"

        await eventually(known, what=f"the Gateway to know {slug}")

    async def rule(self, **overrides: Any) -> dict[str, Any]:
        """Create a rule. Defaults: Exact `GET /echo/mocked`, one 200 response."""
        response = await self.api.post(
            ME_RULES, json=rule_body(**{"pattern": "/echo/mocked", **overrides})
        )
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created

    async def toggle(self, rule: dict[str, Any], enabled: bool) -> None:
        await self.post(f"/me/rules/{rule['id']}/toggle", {"isEnabled": enabled})

    async def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """A request through the Gateway at this Developer's address."""
        assert self.slug, "claim a slug first"
        return await self.stack.gateway_client.request(method, f"/{self.slug}{path}", **kwargs)

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.call("GET", path, **kwargs)

    async def becomes(self, path: str, *, source: str, within: float = TWO_SECONDS) -> float:
        """Poll `GET path` until `X-Mockan-Source` is `source`; returns the seconds it took."""

        async def check() -> bool:
            return (await self.get(path)).headers.get("x-mockan-source") == source

        return await eventually(check, within=within, what=f"{path} to be `{source}`")


async def eventually(
    check: Callable[[], Awaitable[bool]],
    *,
    within: float = TWO_SECONDS,
    what: str = "the condition",
) -> float:
    """Poll `check` until it is true; returns the seconds it took, or fails the test."""
    started = time.perf_counter()
    while time.perf_counter() - started < within:
        if await check():
            return time.perf_counter() - started
        await asyncio.sleep(0.02)
    raise AssertionError(f"{what} was not met within {within}s")


@dataclass
class Stack:
    settings: MockanSettings
    admin: LiveServer
    gateway: LiveServer
    upstream: Upstream
    session_factory: async_sessionmaker[AsyncSession]
    gateway_client: httpx.AsyncClient
    clients: list[httpx.AsyncClient] = field(default_factory=list)

    async def sign_in(self, name: str, *, admin: bool = False, slug: str | None = None) -> Person:
        """Dev-mode sign-in (G-9), then optionally claim a slug, like the Panel's onboarding."""
        api = httpx.AsyncClient(base_url=self.admin.url, trust_env=False, timeout=30)
        self.clients.append(api)
        login = await api.get(
            "/api/v1/auth/login", params={"as": name, **({"admin": "1"} if admin else {})}
        )
        assert login.status_code == 303, login.text
        person = Person(self, api)
        if slug:
            await person.claim(slug)
        return person

    async def add_service(
        self,
        admin: Person,
        name: str,
        *,
        stage: str | None = None,
        dev: str | None = None,
        strip_prefix: bool = False,
        default: str = "stage",
        prefix: str | None = None,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        """A Service whose environments point at the given base URLs (default: the upstream)."""
        service = (
            await admin.post(
                "/services",
                {
                    "name": name,
                    "pathPrefix": prefix or f"/{name}",
                    "stripPrefix": strip_prefix,
                    "defaultEnvironment": default,
                },
                expect=201,
            )
        ).json()
        for environment, url in (("stage", stage or self.upstream.url), ("dev", dev)):
            if url:
                await admin.post(
                    f"/services/{service['id']}/environments",
                    {"environment": environment, "baseUrl": url, "timeoutSeconds": timeout_seconds},
                    expect=201,
                )
        return service

    async def add_upstream_routes(self, admin: Person) -> None:
        for name in UPSTREAM_ROUTES:
            await self.add_service(admin, name)


@pytest.fixture
def start_upstream() -> Callable[[], Upstream]:
    """Start more fake upstreams (for environment switching); stopped when the test ends."""
    started: list[LiveServer] = []

    def start() -> Upstream:
        state = UpstreamState()
        server = LiveServer(build_fake_upstream(state), lifespan="off").start()
        started.append(server)
        return Upstream(server, state)

    yield start  # type: ignore[misc]
    for server in started:
        server.stop()


@pytest.fixture
async def stack(
    pg_container: str,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    start_upstream: Callable[[], Upstream],
) -> AsyncIterator[Stack]:
    upstream = start_upstream()
    settings = MockanSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=pg_container,
        auth_mode="dev",
        session_secret="acceptance-" * 4,
        admin_sso_subjects=["dev:root"],
        allowed_upstream_hosts=[upstream.server.host],
        public_base_url=PUBLIC_BASE_URL,
        snapshot_debounce_ms=20,
        log_level="WARNING",
    )
    admin = LiveServer(create_admin(settings)).start()
    gateway = LiveServer(create_gateway(settings)).start()
    client = httpx.AsyncClient(base_url=gateway.url, trust_env=False, timeout=30)
    current = Stack(settings, admin, gateway, upstream, session_factory, client)

    async def ready() -> bool:  # the first snapshot is loaded when readiness turns 200
        return (await client.get("/_mockan/health/ready")).status_code == 200

    await eventually(ready, within=10, what="the Gateway to be ready")
    try:
        yield current
    finally:
        for opened in (*current.clients, client):
            await opened.aclose()
        gateway.stop()
        admin.stop()


@pytest.fixture
async def root(stack: Stack) -> Person:
    """An admin (`MOCKAN_ADMIN_SSO_SUBJECTS` lists `dev:root`) with the catalog registered."""
    person = await stack.sign_in("root")
    await person.claim("root")
    await stack.add_upstream_routes(person)
    return person


__all__ = ["PUBLIC_BASE_URL", "TWO_SECONDS", "Person", "Stack", "response_body"]
