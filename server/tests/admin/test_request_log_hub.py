"""`/hubs/request-log`: new entries reach the Developer's open sockets (PR-12, D-18, D-19).

A live Admin on a real socket, the real writer and a real `websockets` client; the only thing
faked is the Gateway's request (an entry offered to the queue the Gateway's writer consumes).
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import websockets
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.exceptions import InvalidStatus

from mockan.admin.app import create_app
from mockan.infrastructure.request_log import RequestLogQueue, RequestLogWriter
from mockan.infrastructure.settings import MockanSettings
from tests.infrastructure.test_request_log import entry
from tests.support.live_server import LiveServer

pytestmark = [pytest.mark.db, pytest.mark.req("PR-12")]


@pytest.fixture
def live_admin(admin_settings: MockanSettings, engine: object) -> Iterator[LiveServer]:
    server = LiveServer(create_app(admin_settings)).start()  # its own engine and hub
    yield server
    server.stop()


@pytest.fixture
async def gateway_side(
    admin_settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[RequestLogQueue]:
    """What a Gateway does: a queue drained by the real writer."""
    queue = RequestLogQueue(100)
    writer = RequestLogWriter(
        admin_settings.model_copy(update={"request_log_flush_ms": 20}), session_factory, queue
    )
    await writer.start()
    yield queue
    await writer.stop()


async def sign_in(server: LiveServer, name: str) -> tuple[httpx.AsyncClient, uuid.UUID]:
    client = httpx.AsyncClient(base_url=server.url, trust_env=False)
    await client.get("/api/v1/auth/login", params={"as": name})
    return client, uuid.UUID((await client.get("/api/v1/me")).json()["id"])


def socket_for(server: LiveServer, client: httpx.AsyncClient) -> websockets.connect:
    cookie = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    return websockets.connect(
        f"{server.ws_url}/hubs/request-log", additional_headers={"Cookie": cookie}
    )


async def next_entry(socket: websockets.ClientConnection, within: float = 3) -> dict[str, object]:
    return json.loads(await asyncio.wait_for(socket.recv(), within))  # type: ignore[no-any-return]


async def test_new_entries_are_pushed_to_the_developers_socket_and_to_nobody_else(
    live_admin: LiveServer, gateway_side: RequestLogQueue
) -> None:
    (alice, alice_id), (bob, bob_id) = (
        await sign_in(live_admin, "alice"),
        await sign_in(live_admin, "bob"),
    )
    async with socket_for(live_admin, alice) as a, socket_for(live_admin, bob) as b:
        await asyncio.sleep(0.3)  # both subscribed
        gateway_side.offer(
            entry(alice_id, path="/for-alice", request_headers=[(b"authorization", b"x")])
        )
        gateway_side.offer(entry(bob_id, path="/for-bob"))
        gateway_side.offer(entry(alice_id, path="/for-alice-2"))

        first, second = await next_entry(a), await next_entry(a)
        only = await next_entry(b)

        assert [first["path"], second["path"]] == ["/for-alice", "/for-alice-2"]  # in order
        assert only["path"] == "/for-bob"
        assert first["developerId"] == str(alice_id)
        assert first["requestHeaders"] == {"authorization": "***"}  # masked, like the REST list
        assert set(first) == {
            "id", "developerId", "timestamp", "method", "path", "query", "serviceId", "source",
            "ruleId", "statusCode", "durationMs", "requestHeaders", "responseHeaders",
            "requestBodySample", "responseBodySample",
        }  # fmt: skip
        with pytest.raises(TimeoutError):
            await next_entry(b, within=0.5)  # nothing of alice's leaked to bob
    await alice.aclose()
    await bob.aclose()


async def test_a_socket_only_gets_entries_newer_than_when_it_connected(
    live_admin: LiveServer,
    gateway_side: RequestLogQueue,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, developer_id = await sign_in(live_admin, "alice")
    gateway_side.offer(entry(developer_id, path="/before"))
    await asyncio.sleep(0.4)  # written before the socket exists: history is the REST list's job
    async with socket_for(live_admin, client) as socket:
        await asyncio.sleep(0.3)
        gateway_side.offer(entry(developer_id, path="/after"))

        assert (await next_entry(socket))["path"] == "/after"
    await client.aclose()


async def test_every_socket_of_a_developer_gets_every_entry(
    live_admin: LiveServer, gateway_side: RequestLogQueue
) -> None:
    client, developer_id = await sign_in(live_admin, "alice")
    async with socket_for(live_admin, client) as one, socket_for(live_admin, client) as two:
        await asyncio.sleep(0.3)
        for i in range(5):
            gateway_side.offer(entry(developer_id, path=f"/n{i}"))

        got_one = [(await next_entry(one))["path"] for _ in range(5)]
        got_two = [(await next_entry(two))["path"] for _ in range(5)]

        assert got_one == got_two == [f"/n{i}" for i in range(5)]
    await client.aclose()


async def test_a_closed_socket_stops_receiving_and_the_hub_keeps_working(
    live_admin: LiveServer, gateway_side: RequestLogQueue
) -> None:
    client, developer_id = await sign_in(live_admin, "alice")
    async with socket_for(live_admin, client) as gone:
        await asyncio.sleep(0.3)
    gateway_side.offer(entry(developer_id, path="/nobody-listens"))
    await asyncio.sleep(0.4)
    async with socket_for(live_admin, client) as socket:
        await asyncio.sleep(0.3)
        gateway_side.offer(entry(developer_id, path="/new-socket"))

        assert (await next_entry(socket))["path"] == "/new-socket"
    assert gone is not None
    await client.aclose()


async def test_a_socket_without_a_session_is_refused(live_admin: LiveServer) -> None:
    with pytest.raises(InvalidStatus) as refused:
        async with websockets.connect(f"{live_admin.ws_url}/hubs/request-log"):
            pass

    assert refused.value.response.status_code == 403


async def test_a_socket_with_a_bad_cookie_is_refused(live_admin: LiveServer) -> None:
    with pytest.raises(InvalidStatus):
        async with websockets.connect(
            f"{live_admin.ws_url}/hubs/request-log",
            additional_headers={"Cookie": "mockan_session=forged"},
        ):
            pass
