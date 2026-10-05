"""Masking, the batch writer, notifications and retention of the request log (PR-12, NFR-07)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.constants import SAMPLE_BYTES
from mockan.domain.enums import RequestSource
from mockan.infrastructure.db.models import RequestLog
from mockan.infrastructure.request_log import (
    CHANNEL,
    LogEntry,
    RequestLogQueue,
    RequestLogWriter,
    prune,
    sample_text,
    to_row,
)
from mockan.infrastructure.settings import MockanSettings
from tests.support.notify_listener import Listener

JSON = [(b"content-type", b"application/json; charset=utf-8")]


def entry(developer_id: uuid.UUID | None = None, **overrides: object) -> LogEntry:
    values: dict[str, object] = {
        "developer_id": developer_id or uuid.uuid4(),
        "timestamp": datetime.now(UTC),
        "method": "GET",
        "path": "/limsa/x",
        "query": "",
        "service_id": None,
        "source": RequestSource.PROXIED,
        "rule_id": None,
        "status_code": 200,
        "duration_ms": 3,
        "request_headers": [],
        "response_headers": [],
        "request_sample": b"",
        "response_sample": b"",
    }
    return LogEntry(**{**values, **overrides})  # type: ignore[arg-type]


# ---- masking (NFR-07), no database ------------------------------------------------------------


@pytest.mark.req("PR-15")
def test_headers_are_masked_and_lower_cased() -> None:
    row = to_row(
        entry(
            request_headers=[
                (b"Authorization", b"Bearer hunter2"),
                (b"Cookie", b"sid=1"),
                (b"X-Api-Key", b"k"),
                (b"Accept", b"*/*"),
                (b"Accept", b"text/html"),
            ],
            response_headers=[(b"Set-Cookie", b"sid=2"), (b"X-Keep", b"yes")],
        )
    )

    assert row["request_headers"] == {
        "authorization": "***",
        "cookie": "***",
        "x-api-key": "***",
        "accept": "*/*, text/html",
    }
    assert row["response_headers"] == {"set-cookie": "***", "x-keep": "yes"}


@pytest.mark.req("PR-15")
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            b'{"user":"a","password":"p","nested":{"apiKey":"k","ok":1}}',
            {"user": "a", "password": "***", "nested": {"apiKey": "***", "ok": 1}},
        ),
        (b'[{"access_token":"t"},{"name":"n"}]', [{"access_token": "***"}, {"name": "n"}]),
    ],
)
def test_json_bodies_are_masked_by_key(body: bytes, expected: object) -> None:
    assert json.loads(sample_text(body, JSON) or "") == expected


@pytest.mark.req("PR-15")
def test_a_json_body_cut_at_16_kb_is_still_masked() -> None:
    cut = b'{"ok":true,"client_secret":"abc","items":[1,2,{"note":"x' + b"y" * 50  # not valid JSON

    masked = sample_text(cut, JSON) or ""

    assert '"client_secret":"***"' in masked
    assert "abc" not in masked
    assert '"ok":true' in masked


@pytest.mark.req("PR-15")
def test_form_bodies_are_masked_by_field() -> None:
    form = [(b"content-type", b"application/x-www-form-urlencoded")]

    masked = sample_text(b"grant_type=password&username=e&password=hunter2&client_secret=s", form)

    assert masked == "grant_type=password&username=e&password=***&client_secret=***"


def test_text_is_kept_binary_encoded_and_empty_bodies_are_not_stored() -> None:
    assert sample_text(b"hello \xff\x00world", [(b"content-type", b"text/plain")]) == "hello �world"
    assert sample_text(b"\x89PNG", [(b"content-type", b"image/png")]) is None
    assert (
        sample_text(b"{}", [(b"content-type", b"application/json"), (b"content-encoding", b"gzip")])
        is None
    )
    assert sample_text(b"", JSON) is None
    assert sample_text(b"{}", []) is None  # no content type: not known to be text


def test_a_json_looking_body_with_a_text_type_is_masked_too() -> None:
    plain = [(b"content-type", b"text/plain")]

    assert json.loads(sample_text(b'{"password":"p"}', plain) or "") == {"password": "***"}


def test_samples_never_exceed_16_kb_and_long_values_are_truncated() -> None:
    row = to_row(
        entry(
            path="/" + "p" * 10_000,
            method="PROPFIND-WITH-A-LONG-NAME",
            request_sample=b"x" * 40_000,
            request_headers=[(b"content-type", b"text/plain"), (b"x-long", b"v" * 5000)],
        )
    )

    assert len(row["request_body_sample"].encode()) == SAMPLE_BYTES
    assert len(row["path"]) == 4096
    assert len(row["method"]) == 16
    assert len(row["request_headers"]["x-long"]) == 2048


# ---- the writer (needs Docker) ----------------------------------------------------------------


Factory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def request_logged(pg_container: str, engine: object) -> AsyncIterator[Listener]:
    connection = await asyncpg.connect(pg_container.replace("+asyncpg", ""))
    listener = Listener()
    await connection.add_listener(CHANNEL, listener)
    yield listener
    await connection.close()


def writer_for(
    pg_container: str, factory: Factory, queue: RequestLogQueue, **settings: object
) -> RequestLogWriter:
    config = MockanSettings(_env_file=None, database_url=pg_container, **settings)  # type: ignore[call-arg, arg-type]
    return RequestLogWriter(config, factory, queue)


async def rows(factory: Factory) -> list[RequestLog]:
    async with factory() as session:
        return list(await session.scalars(select(RequestLog).order_by(RequestLog.id)))


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_a_batch_is_inserted_masked_and_notified_per_developer(
    pg_container: str, session_factory: Factory, request_logged: Listener
) -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()
    queue = RequestLogQueue(100)
    writer = writer_for(pg_container, session_factory, queue, request_log_flush_ms=50)
    await writer.start()
    try:
        for developer, path in ((alice, "/a1"), (alice, "/a2"), (bob, "/b1")):
            queue.offer(
                entry(
                    developer,
                    path=path,
                    request_headers=[(b"authorization", b"Bearer hunter2")],
                    response_headers=JSON,
                    response_sample=b'{"password":"p","ok":1}',
                )
            )
        payloads = await request_logged.payloads(2)
    finally:
        await writer.stop()

    saved = await rows(session_factory)
    assert [r.path for r in saved] == ["/a1", "/a2", "/b1"]
    assert saved[0].request_headers == {"authorization": "***"}
    assert json.loads(saved[0].response_body_sample or "") == {"password": "***", "ok": 1}
    assert (saved[0].source, saved[0].status_code, saved[0].duration_ms) == (
        RequestSource.PROXIED,
        200,
        3,
    )
    assert saved[0].timestamp.tzinfo is not None
    # D-19: one notification per Developer in the batch, naming the newest id.
    assert sorted(payloads) == sorted([f"{alice}:{saved[1].id}", f"{bob}:{saved[2].id}"])
    assert writer.written == 3


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_entries_still_queued_at_shutdown_are_flushed(
    pg_container: str, session_factory: Factory, engine: object
) -> None:
    queue = RequestLogQueue(100)
    writer = writer_for(pg_container, session_factory, queue, request_log_flush_ms=60_000)
    for i in range(5):
        queue.offer(entry(path=f"/q{i}"))
    await writer.stop()

    assert [r.path for r in await rows(session_factory)] == [f"/q{i}" for i in range(5)]


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_a_failing_batch_is_dropped_and_counted_and_the_writer_keeps_going(
    pg_container: str, session_factory: Factory, engine: object
) -> None:
    queue = RequestLogQueue(100)
    writer = writer_for(pg_container, session_factory, queue, request_log_flush_ms=30)
    await writer.start()
    try:
        queue.offer(entry(status_code=99999999999))  # does not fit an INTEGER column
        await asyncio.sleep(0.5)
        queue.offer(entry(path="/after"))
        for _ in range(100):
            if writer.written:
                break
            await asyncio.sleep(0.05)
    finally:
        await writer.stop()

    assert (writer.failed, queue.dropped) == (1, 1)
    assert [r.path for r in await rows(session_factory)] == ["/after"]


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_batches_respect_the_batch_size(
    pg_container: str, session_factory: Factory, request_logged: Listener
) -> None:
    queue = RequestLogQueue(100)
    developer = uuid.uuid4()
    for i in range(7):
        queue.offer(entry(developer, path=f"/b{i}"))
    writer = writer_for(
        pg_container, session_factory, queue, request_log_batch_size=3, request_log_flush_ms=20
    )
    await writer.start()
    try:
        notifications = await request_logged.payloads(3)  # 3 + 3 + 1 entries = 3 batches
    finally:
        await writer.stop()

    assert len(notifications) == 3
    assert len(await rows(session_factory)) == 7


# ---- retention --------------------------------------------------------------------------------


async def insert_rows(
    factory: Factory, developer: uuid.UUID, count: int, *, age_days: int = 0
) -> None:
    async with factory() as session:
        for i in range(count):
            row = to_row(entry(developer, path=f"/{developer.hex[:4]}/{i}"))
            row["timestamp"] = datetime.now(UTC) - timedelta(days=age_days)
            session.add(RequestLog(**row))
        await session.commit()


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_prune_removes_old_rows_and_rows_beyond_the_cap_per_developer(
    session_factory: Factory, engine: object
) -> None:
    busy, quiet = uuid.uuid4(), uuid.uuid4()
    await insert_rows(session_factory, busy, 8)
    await insert_rows(session_factory, quiet, 3)
    await insert_rows(session_factory, quiet, 2, age_days=8)

    deleted = await prune(session_factory, days=7, max_rows=5)

    assert deleted == {"expired": 2, "over_cap": 3}
    saved = await rows(session_factory)
    assert sum(r.developer_id == busy for r in saved) == 5
    assert sum(r.developer_id == quiet for r in saved) == 3
    busy_paths = [r.path for r in saved if r.developer_id == busy]
    assert busy_paths == [f"/{busy.hex[:4]}/{i}" for i in range(3, 8)]  # the newest five stay


@pytest.mark.db
@pytest.mark.req("PR-12")
async def test_only_one_gateway_prunes_at_a_time(
    pg_container: str, session_factory: Factory, engine: object
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    await insert_rows(session_factory, uuid.uuid4(), 3, age_days=30)
    holder_engine = create_async_engine(pg_container)
    async with holder_engine.connect() as holder, holder.begin():
        await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 0x4D4F434B})

        assert (
            await prune(session_factory, days=7, max_rows=5000) is None
        )  # someone else is pruning
        assert len(await rows(session_factory)) == 3

    assert await prune(session_factory, days=7, max_rows=5000) == {"expired": 3, "over_cap": 0}
    await holder_engine.dispose()
