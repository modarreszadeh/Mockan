"""The request log pipeline (PR-12, D-18, D-19): a bounded queue, a batch writer and retention.

The Gateway puts a `LogEntry` on a `RequestLogQueue` without waiting (`offer`; a full queue drops
the entry and counts it), so logging never slows a request. A background `RequestLogWriter` takes
entries in batches, **masks** them (NFR-07), inserts them and sends
`pg_notify('mockan_request_logged', '<developerId>:<maxId>')` for the Admin's live view (D-19).
Retention keeps 7 days and 5,000 rows per Developer.
"""

import asyncio
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode

import structlog
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.constants import SAMPLE_BYTES
from mockan.domain.enums import RequestSource
from mockan.infrastructure.db.models import RequestLog
from mockan.infrastructure.masking import MASK, is_sensitive_name, mask_headers, mask_json
from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

CHANNEL = "mockan_request_logged"
_RETENTION_LOCK = 0x4D4F434B  # advisory lock key: only one Gateway prunes at a time
_MAX_HEADERS = 100
_MAX_HEADER_VALUE = 2048
_MAX_PATH = 4096
_TEXTUAL = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "graphql", "yaml")
_JSON_PAIR = re.compile(
    r'("(?:[^"\\]|\\.)*"\s*:\s*)("(?:[^"\\]|\\.)*"|[^,}\]\s"][^,}\]\s]*)'
)  # "key": value, also in a body cut at 16 KB


@dataclass(slots=True)
class LogEntry:
    """What the Gateway knows when a request ends. Raw: masking happens in the writer."""

    developer_id: uuid.UUID
    timestamp: datetime
    method: str
    path: str
    query: str
    service_id: uuid.UUID | None
    source: RequestSource
    rule_id: uuid.UUID | None
    status_code: int
    duration_ms: int
    request_headers: Sequence[tuple[bytes, bytes]]
    response_headers: Sequence[tuple[bytes, bytes]]
    request_sample: bytes
    response_sample: bytes


class RequestLogQueue:
    """A bounded `asyncio.Queue`; `offer` never waits (arch §14 rule 10)."""

    def __init__(self, maxsize: int) -> None:
        self._queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def offer(self, entry: LogEntry) -> bool:
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            self.dropped += 1  # mockan_request_log_dropped_total
            return False
        return True

    async def get(self) -> LogEntry:
        return await self._queue.get()

    def get_nowait(self) -> LogEntry:
        return self._queue.get_nowait()

    def qsize(self) -> int:
        return self._queue.qsize()


# ---- masking and sample preparation (runs in a worker thread) --------------------------------


def _headers(raw: Sequence[tuple[bytes, bytes]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in raw[:_MAX_HEADERS]:
        key = name.decode("latin-1").lower()
        text_value = value.decode("latin-1")[:_MAX_HEADER_VALUE]
        result[key] = f"{result[key]}, {text_value}" if key in result else text_value
    return mask_headers(result)


def _header(raw: Sequence[tuple[bytes, bytes]], name: bytes) -> str:
    for key, value in raw:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def _mask_json_text(text_value: str) -> str:
    try:
        parsed = json.loads(text_value)
        masked = mask_json(parsed)
        if masked == parsed:
            return text_value  # nothing secret in it: keep the body exactly as it was sent
        return json.dumps(masked, ensure_ascii=False, separators=(",", ":"))
    except ValueError:  # cut at 16 KB, or not JSON after all: mask key by key

        def replace(match: re.Match[str]) -> str:
            key = match.group(1).split('"', 2)[1]
            return f'{match.group(1)}"{MASK}"' if is_sensitive_name(key) else match.group(0)

        return _JSON_PAIR.sub(replace, text_value)


def _mask_form(text_value: str) -> str:
    pairs = parse_qsl(text_value, keep_blank_values=True)
    return urlencode([(k, MASK if is_sensitive_name(k) else v) for k, v in pairs], safe="*")


def sample_text(sample: bytes, headers: Sequence[tuple[bytes, bytes]]) -> str | None:
    """A body sample as masked text, or `None` for empty, encoded or binary bodies."""
    if not sample:
        return None
    encoding = _header(headers, b"content-encoding").strip().lower()
    content_type = _header(headers, b"content-type").lower()
    if encoding not in ("", "identity") or not any(kind in content_type for kind in _TEXTUAL):
        return None
    decoded = sample[:SAMPLE_BYTES].decode("utf-8", errors="replace").replace("\0", "")
    if "x-www-form-urlencoded" in content_type:
        return _mask_form(decoded)
    if "json" in content_type or decoded.lstrip().startswith(("{", "[")):
        return _mask_json_text(decoded)
    return decoded


def to_row(entry: LogEntry) -> dict[str, Any]:
    """The `request_logs` row for an entry, with every secret masked (NFR-07)."""
    return {
        "developer_id": entry.developer_id,
        "timestamp": entry.timestamp,
        "method": entry.method[:16],
        "path": entry.path[:_MAX_PATH],
        "query": entry.query[:_MAX_PATH],
        "service_id": entry.service_id,
        "source": entry.source,
        "rule_id": entry.rule_id,
        "status_code": entry.status_code,
        "duration_ms": entry.duration_ms,
        "request_headers": _headers(entry.request_headers),
        "response_headers": _headers(entry.response_headers),
        "request_body_sample": sample_text(entry.request_sample, entry.request_headers),
        "response_body_sample": sample_text(entry.response_sample, entry.response_headers),
    }


# ---- the writer -------------------------------------------------------------------------------


class RequestLogWriter:
    """Background task: queue -> batches -> `request_logs` (+ notify); plus the retention loop."""

    def __init__(
        self,
        settings: MockanSettings,
        session_factory: async_sessionmaker[AsyncSession],
        queue: RequestLogQueue,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._queue = queue
        self._tasks: list[asyncio.Task[None]] = []
        self.written = 0
        self.failed = 0  # entries lost to a database error (also counted as dropped)

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._write_loop(), name="mockan-request-log-writer"),
            asyncio.create_task(self._retention_loop(), name="mockan-request-log-retention"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        rest: list[LogEntry] = []
        while True:  # best effort: what is still queued at shutdown
            try:
                rest.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if rest:
            try:
                await asyncio.wait_for(self.write_batch(rest), timeout=5)
            except Exception as error:
                log.warning("request_log_flush_failed", entries=len(rest), error=repr(error))

    async def _next_batch(self) -> list[LogEntry]:
        batch = [await self._queue.get()]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.request_log_flush_ms / 1000
        while len(batch) < self._settings.request_log_batch_size:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
            except TimeoutError:
                break
        return batch

    async def _write_loop(self) -> None:
        while True:
            batch = await self._next_batch()
            try:
                await self.write_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # a bad batch must not kill the logger
                self.failed += len(batch)
                self._queue.dropped += len(batch)
                log.warning("request_log_write_failed", entries=len(batch), error=repr(error))

    async def write_batch(self, batch: Sequence[LogEntry]) -> None:
        rows = await asyncio.to_thread(lambda: [to_row(entry) for entry in batch])
        async with self._session_factory() as session:
            result = await session.execute(
                insert(RequestLog).returning(RequestLog.id, RequestLog.developer_id), rows
            )
            newest: dict[uuid.UUID, int] = {}
            for log_id, developer_id in result:
                newest[developer_id] = max(newest.get(developer_id, 0), log_id)
            for developer_id, max_id in newest.items():  # D-19: the Admin pushes it to the Panel
                await session.execute(
                    text("SELECT pg_notify(:channel, :payload)"),
                    {"channel": CHANNEL, "payload": f"{developer_id}:{max_id}"},
                )
            await session.commit()
        self.written += len(batch)

    async def _retention_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.request_log_cleanup_seconds)
            try:
                await prune(
                    self._session_factory,
                    days=self._settings.request_log_retention_days,
                    max_rows=self._settings.request_log_max_rows_per_developer,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("request_log_prune_failed", error=repr(error))


async def prune(
    session_factory: async_sessionmaker[AsyncSession], *, days: int, max_rows: int
) -> Mapping[str, int] | None:
    """Delete rows older than `days` and rows beyond the newest `max_rows` per Developer.

    Several Gateways run this loop; an advisory lock lets one of them do the work (`None` = another
    one is pruning). Returns how many rows each rule deleted.
    """
    async with session_factory() as session:
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _RETENTION_LOCK}
        )
        if not locked:
            return None
        old = await session.execute(
            text(
                "DELETE FROM mockan.request_logs"
                " WHERE timestamp < now() - make_interval(days => :days)"
            ),
            {"days": days},
        )
        over = await session.execute(
            text(
                "DELETE FROM mockan.request_logs r USING ("
                " SELECT id, row_number() OVER"
                " (PARTITION BY developer_id ORDER BY id DESC) AS position"
                " FROM mockan.request_logs) ranked"
                " WHERE r.id = ranked.id AND ranked.position > :max_rows"
            ),
            {"max_rows": max_rows},
        )
        await session.commit()
    result = {
        "expired": int(getattr(old, "rowcount", 0) or 0),
        "over_cap": int(getattr(over, "rowcount", 0) or 0),
    }
    if result["expired"] or result["over_cap"]:
        log.info("request_log_pruned", **result)
    return result


def now() -> datetime:
    return datetime.now(UTC)
