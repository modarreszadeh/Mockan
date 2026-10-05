"""Keeps the Gateway's in-memory snapshot fresh (D-07, FR-08, PR-07).

Three jobs, all in the background (never on the request path, NFR-02):

* a dedicated asyncpg connection runs `LISTEN mockan_config_changed`;
* notifications are debounced, then rebuild one Developer's slice (a Developer id) or the whole
  snapshot (`catalog`);
* a full reload runs every `MOCKAN_SNAPSHOT_RELOAD_SECONDS`, and after every (re)connect, because
  notifications sent while disconnected are lost.

If the database fails the last snapshot keeps serving and the service reports `degraded`.
"""

import asyncio
import time
import uuid

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.infrastructure.db.notify import CATALOG, CHANNEL
from mockan.infrastructure.settings import MockanSettings
from mockan.infrastructure.snapshot_loader import load_developer, load_full
from mockan.matching.snapshot import RuleSnapshotProvider

log = structlog.get_logger()

LISTENER_APPLICATION_NAME = "mockan-gateway-listener"


class Backoff:
    """Exponential delays: `initial`, 2x, 4x ... capped at `maximum`."""

    def __init__(self, initial: float = 0.5, maximum: float = 30.0) -> None:
        self._initial = initial
        self._maximum = maximum
        self._current = initial

    def next(self) -> float:
        delay = self._current
        self._current = min(self._current * 2, self._maximum)
        return delay

    def reset(self) -> None:
        self._current = self._initial


class SnapshotService:
    def __init__(
        self,
        settings: MockanSettings,
        provider: RuleSnapshotProvider,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        backoff_initial: float = 0.5,
        backoff_max: float = 30.0,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._session_factory = session_factory
        self._backoff = (backoff_initial, backoff_max)
        self._pending: set[str] = set()
        self._wake = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._listening = False
        self._reload_failed = False
        self._last_sync: float | None = None

    # -- status ---------------------------------------------------------------------------------

    @property
    def degraded(self) -> bool:
        """Serving the last good snapshot while the LISTEN connection or a reload is failing."""
        return self._reload_failed or not self._listening

    @property
    def age_seconds(self) -> float | None:
        """Seconds since the snapshot was last brought up to date; `None` before the first load."""
        return None if self._last_sync is None else time.monotonic() - self._last_sync

    # -- lifecycle ------------------------------------------------------------------------------

    async def start(self) -> None:
        self._request_full_reload()
        self._tasks = [
            asyncio.create_task(self._listen_loop(), name="mockan-snapshot-listener"),
            asyncio.create_task(self._reload_loop(), name="mockan-snapshot-reloader"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    # -- notifications --------------------------------------------------------------------------

    def _request_full_reload(self) -> None:
        self._pending.add(CATALOG)
        self._wake.set()

    def _on_notify(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        self._pending.add(payload)
        self._wake.set()

    async def _listen_loop(self) -> None:
        backoff = Backoff(*self._backoff)
        while True:
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(
                    self._settings.database_dsn,
                    timeout=10,
                    server_settings={"application_name": LISTENER_APPLICATION_NAME},
                )
                closed = asyncio.Event()
                connection.add_termination_listener(lambda _c, done=closed: done.set())
                await connection.add_listener(CHANNEL, self._on_notify)
                self._listening = True
                backoff.reset()
                log.info("snapshot_listening", channel=CHANNEL)
                self._request_full_reload()  # anything sent while we were away was lost
                await closed.wait()
                log.warning("snapshot_listener_disconnected")
            except Exception as error:  # background task: never die, always reconnect
                log.warning("snapshot_listener_failed", error=repr(error))
            finally:
                self._listening = False
                if connection is not None and not connection.is_closed():
                    await connection.close(timeout=2)
            await asyncio.sleep(backoff.next())

    # -- reloading ------------------------------------------------------------------------------

    async def _reload_loop(self) -> None:
        backoff = Backoff(*self._backoff)
        debounce = self._settings.snapshot_debounce_ms / 1000
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), self._settings.snapshot_reload_seconds)
                timed_out = False
            except TimeoutError:
                timed_out = True
            if not timed_out and debounce:
                await asyncio.sleep(debounce)  # coalesce a burst of notifications
            self._wake.clear()
            pending, self._pending = self._pending, set()
            if timed_out:
                pending.add(CATALOG)  # the periodic safety net (D-07)
            if not pending:
                continue
            try:
                await self._apply(pending)
            except Exception as error:  # background task: keep the last snapshot, retry
                self._reload_failed = True
                self._pending |= pending
                delay = backoff.next()
                log.warning("snapshot_reload_failed", error=repr(error), retry_in_s=delay)
                await asyncio.sleep(delay)
                self._wake.set()
            else:
                self._reload_failed = False
                self._last_sync = time.monotonic()
                backoff.reset()

    async def _apply(self, pending: set[str]) -> None:
        started = time.perf_counter()
        async with self._session_factory() as session:
            # One consistent view of the database for every query of this reload.
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            if CATALOG in pending or not self._provider.loaded:
                snapshot = await load_full(session)
                scope = "full"
            else:
                snapshot = self._provider.current
                for payload in sorted(pending):
                    try:
                        developer_id = uuid.UUID(payload)
                    except ValueError:
                        log.warning("snapshot_payload_ignored", payload=payload)
                        continue
                    part = await load_developer(session, developer_id)
                    snapshot = snapshot.with_developer_slice(
                        developer_id, developer=part.developer, rules=part.rules
                    )
                scope = "developers"
        self._provider.swap(snapshot)  # a single attribute assignment
        log.info(
            "snapshot_reloaded",
            scope=scope,
            developers=len(snapshot.developers_by_slug),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
