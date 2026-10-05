"""The live request log: `/hubs/request-log` pushes new entries to the Panel (D-18, D-19).

The Gateway's writer sends `pg_notify('mockan_request_logged', '<developerId>:<maxId>')` after each
batch. The hub keeps **one** LISTEN connection per Admin process; a notification for a Developer
who has sockets open reads the rows newer than what each socket has seen and pushes them. A socket
starts "now": the Panel loads history with `GET /me/request-logs`.
"""

import asyncio
import uuid
from dataclasses import dataclass, field

import asyncpg
import structlog
from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.schemas.request_log import RequestLogOut
from mockan.infrastructure.db.models import RequestLog
from mockan.infrastructure.request_log import CHANNEL
from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

_BATCH = 500


@dataclass(eq=False)
class Subscriber:
    socket: WebSocket
    last_id: int


@dataclass
class _Room:
    subscribers: set[Subscriber] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RequestLogHub:
    def __init__(
        self, settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._rooms: dict[uuid.UUID, _Room] = {}
        self._task: asyncio.Task[None] | None = None
        self._pushes: set[asyncio.Task[None]] = set()
        self.listening = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen_loop(), name="mockan-request-log-hub")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        for push in list(self._pushes):
            push.cancel()
        await asyncio.gather(*self._pushes, return_exceptions=True)

    # -- sockets ----------------------------------------------------------------------------

    async def subscribe(self, developer_id: uuid.UUID, socket: WebSocket) -> Subscriber:
        async with self._session_factory() as session:
            newest = await session.scalar(
                select(func.coalesce(func.max(RequestLog.id), 0)).where(
                    RequestLog.developer_id == developer_id
                )
            )
        subscriber = Subscriber(socket, int(newest or 0))
        self._rooms.setdefault(developer_id, _Room()).subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, developer_id: uuid.UUID, subscriber: Subscriber) -> None:
        room = self._rooms.get(developer_id)
        if room is None:
            return
        room.subscribers.discard(subscriber)
        if not room.subscribers:
            del self._rooms[developer_id]

    # -- pushing ----------------------------------------------------------------------------

    def _on_notify(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            developer_id = uuid.UUID(payload.split(":", 1)[0])
        except ValueError:
            return
        if developer_id in self._rooms:
            self._schedule(developer_id)

    def _schedule(self, developer_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._push(developer_id))
        self._pushes.add(task)
        task.add_done_callback(self._pushes.discard)

    async def _push(self, developer_id: uuid.UUID) -> None:
        room = self._rooms.get(developer_id)
        if room is None:
            return
        async with room.lock:  # one reader per Developer at a time keeps the order
            while room.subscribers:
                oldest = min(s.last_id for s in room.subscribers)
                async with self._session_factory() as session:
                    rows = list(
                        await session.scalars(
                            select(RequestLog)
                            .where(RequestLog.developer_id == developer_id, RequestLog.id > oldest)
                            .order_by(RequestLog.id)
                            .limit(_BATCH)
                        )
                    )
                if not rows:
                    return
                for entry in rows:
                    message = RequestLogOut.model_validate(entry).model_dump_json(by_alias=True)
                    for subscriber in list(room.subscribers):
                        if entry.id <= subscriber.last_id:
                            continue
                        try:
                            await subscriber.socket.send_text(message)
                        except Exception:  # the Panel went away; its handler will clean up
                            room.subscribers.discard(subscriber)
                            continue
                        subscriber.last_id = entry.id
                if len(rows) < _BATCH:
                    return

    # -- the LISTEN connection --------------------------------------------------------------

    async def _listen_loop(self) -> None:
        delay = 0.5
        while True:
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(self._settings.database_dsn, timeout=10)
                closed = asyncio.Event()
                connection.add_termination_listener(lambda _c, done=closed: done.set())
                await connection.add_listener(CHANNEL, self._on_notify)
                self.listening = True
                delay = 0.5
                for developer_id in list(self._rooms):  # what was missed while disconnected
                    self._schedule(developer_id)
                await closed.wait()
                log.warning("request_log_hub_disconnected")
            except Exception as error:
                log.warning("request_log_hub_failed", error=repr(error))
            finally:
                self.listening = False
                if connection is not None and not connection.is_closed():
                    await connection.close(timeout=2)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
