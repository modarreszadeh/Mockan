"""`/me/request-logs`: the list, its filters and "Mock this" (PR-12, FR-09)."""

import uuid
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.domain.constants import SAMPLE_BYTES
from mockan.domain.enums import AuditAction, AuditEntityType, RequestSource
from mockan.infrastructure.db.models import AuditLog, RequestLog
from mockan.infrastructure.request_log import to_row
from tests.admin.builders import ME_RULES
from tests.admin.conftest import AsDeveloper
from tests.infrastructure.test_request_log import JSON, entry

pytestmark = [pytest.mark.db, pytest.mark.req("PR-12")]

LOGS = "/api/v1/me/request-logs"
AuditRows = Callable[[], Awaitable[list[AuditLog]]]


async def add_logs(
    factory: async_sessionmaker[AsyncSession],
    developer: uuid.UUID,
    *paths: str,
    **overrides: object,
) -> list[int]:
    async with factory() as session:
        saved = [RequestLog(**to_row(entry(developer, path=path, **overrides))) for path in paths]
        session.add_all(saved)
        await session.commit()
        return [row.id for row in saved]


async def test_the_list_is_newest_first_and_carries_the_panel_contract(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    first, second = await add_logs(
        session_factory,
        developer.id,
        "/a",
        "/b",
        source=RequestSource.MOCKED,
        request_headers=[(b"authorization", b"Bearer x"), (b"x-a", b"1")],
        response_headers=JSON,
        response_sample=b'{"ok":true}',
    )

    page = (await admin_client.get(LOGS)).json()

    assert page["nextCursor"] is None
    assert [item["id"] for item in page["items"]] == [second, first]
    item = page["items"][0]
    assert set(item) == {
        "id",
        "developerId",
        "timestamp",
        "method",
        "path",
        "query",
        "serviceId",
        "source",
        "ruleId",
        "statusCode",
        "durationMs",
        "requestHeaders",
        "responseHeaders",
        "requestBodySample",
        "responseBodySample",
    }
    assert item["developerId"] == str(developer.id)
    assert (item["source"], item["path"], item["statusCode"]) == ("Mocked", "/b", 200)
    assert item["requestHeaders"] == {"authorization": "***", "x-a": "1"}
    assert item["responseBodySample"] == '{"ok":true}'
    assert item["timestamp"].endswith("Z")


async def test_an_empty_log_is_an_empty_page(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    assert (await admin_client.get(LOGS)).json() == {"items": [], "nextCursor": None}


async def test_paging_walks_back_through_every_entry_once(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    ids = await add_logs(session_factory, developer.id, *[f"/p{i}" for i in range(7)])

    seen: list[int] = []
    cursor: str | None = None
    pages = 0
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = (await admin_client.get(LOGS, params=params)).json()
        seen += [item["id"] for item in page["items"]]
        pages += 1
        cursor = page["nextCursor"]
        if cursor is None:
            break

    assert seen == sorted(ids, reverse=True)
    assert pages == 3


async def test_filters_by_source_and_by_path_text(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    await add_logs(session_factory, developer.id, "/limsa/Dashboard", "/limsa/orders/50%")
    await add_logs(session_factory, developer.id, "/identity/token", source=RequestSource.MOCKED)
    await add_logs(session_factory, developer.id, "/limsa/boom", source=RequestSource.ERROR)

    async def paths(**params: str) -> list[str]:
        return [i["path"] for i in (await admin_client.get(LOGS, params=params)).json()["items"]]

    assert await paths(source="Mocked") == ["/identity/token"]
    assert await paths(source="Error") == ["/limsa/boom"]
    assert await paths(path="dashboard") == ["/limsa/Dashboard"]  # case-insensitive
    assert await paths(path="50%") == ["/limsa/orders/50%"]  # `%` is text, not a wildcard
    assert await paths(path="_") == []  # and so is `_`
    assert await paths(path="/limsa", source="Error") == ["/limsa/boom"]


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "abc"},
        {"cursor": "0"},
        {"cursor": "-5"},
        {"limit": "0"},
        {"limit": "201"},
        {"source": "Nope"},
    ],
)
async def test_bad_parameters_are_422(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper, params: dict[str, str]
) -> None:
    await as_developer("ehtesham")

    response = await admin_client.get(LOGS, params=params)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.mark.req("PR-01")
async def test_a_developer_only_sees_their_own_entries(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alice = await as_developer("alice")
    bob = await as_developer("bob")
    (alices,) = await add_logs(session_factory, alice.id, "/alice")
    await add_logs(session_factory, bob.id, "/bob")

    assert [i["path"] for i in (await admin_client.get(LOGS)).json()["items"]] == ["/bob"]
    assert (await admin_client.post(f"{LOGS}/{alices}/create-rule")).status_code == 404
    assert (await admin_client.get(ME_RULES)).json() == []


async def test_the_log_needs_a_session(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get(LOGS)).status_code == 401
    assert (await admin_client.post(f"{LOGS}/1/create-rule")).status_code == 401


# ---- "Mock this" (FR-09) ---------------------------------------------------------------------


async def test_mock_this_creates_an_exact_rule_from_the_logged_response(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
    audit_rows: AuditRows,
) -> None:
    developer = await as_developer("ehtesham")
    (log_id,) = await add_logs(
        session_factory,
        developer.id,
        "/limsa/api/v1/dashboard",
        status_code=201,
        method="POST",
        response_headers=[
            (b"content-type", b"application/vnd.api+json"),
            (b"content-length", b"11"),
            (b"x-request-id", b"abc"),
            (b"set-cookie", b"sid=1"),
            (b"x-api-key", b"secret"),
            (b"date", b"today"),
            (b"x-mockan-source", b"proxy"),
            (b"access-control-allow-origin", b"http://localhost"),
        ],
        response_sample=b'{"password":"hunter2","ok":1}',
    )

    response = await admin_client.post(f"{LOGS}/{log_id}/create-rule")

    assert response.status_code == 201
    rule = response.json()
    assert (rule["matchType"], rule["method"], rule["pattern"]) == (
        "Exact",
        "POST",
        "/limsa/api/v1/dashboard",
    )
    assert rule["isEnabled"] is True
    assert rule["name"] == "POST /limsa/api/v1/dashboard"
    (scenario,) = rule["responses"]
    assert (scenario["statusCode"], scenario["contentType"]) == (201, "application/vnd.api+json")
    assert scenario["headers"] == {"x-request-id": "abc"}  # secrets, framing and CORS are gone
    assert scenario["body"] == '{"password":"***","ok":1}'  # as logged: masked
    assert rule["activeResponseId"] == scenario["id"]
    assert (await admin_client.get(f"{ME_RULES}/{rule['id']}")).json() == rule
    entry_ = (await audit_rows())[-1]
    assert (entry_.action, entry_.entity_type) == (AuditAction.CREATE, AuditEntityType.MOCK_RULE)


async def test_mock_this_without_a_logged_body_or_content_type_uses_defaults(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    (log_id,) = await add_logs(
        session_factory, developer.id, "/x", status_code=204, method="PROPFIND"
    )

    rule = (await admin_client.post(f"{LOGS}/{log_id}/create-rule")).json()

    assert rule["method"] == "ANY"  # not an HTTP method a rule can name
    (scenario,) = rule["responses"]
    assert (scenario["statusCode"], scenario["contentType"], scenario["body"]) == (
        204,
        "application/json",
        "",
    )


async def test_a_response_cut_at_16_kb_is_refused(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    (log_id,) = await add_logs(
        session_factory,
        developer.id,
        "/big",
        response_headers=[(b"content-type", b"text/plain")],
        response_sample=b"x" * (SAMPLE_BYTES + 10),
    )

    response = await admin_client.post(f"{LOGS}/{log_id}/create-rule")

    assert response.status_code == 422
    assert "16 KB" in response.json()["detail"]
    assert (await admin_client.get(ME_RULES)).json() == []


async def test_a_path_that_cannot_be_an_exact_pattern_is_422_on_pattern(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham")
    (log_id,) = await add_logs(session_factory, developer.id, "/with space/and{braces}")

    response = await admin_client.post(f"{LOGS}/{log_id}/create-rule")

    assert response.status_code == 422
    assert "pattern" in response.json()["errors"]


async def test_mock_this_of_an_unknown_entry_is_404(
    admin_client: httpx.AsyncClient, as_developer: AsDeveloper
) -> None:
    await as_developer("ehtesham")

    for log_id in ("999999", "abc"):
        assert (await admin_client.post(f"{LOGS}/{log_id}/create-rule")).status_code == 404


async def test_a_disabled_developer_can_read_the_log_but_not_mock_from_it(
    admin_client: httpx.AsyncClient,
    as_developer: AsDeveloper,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    developer = await as_developer("ehtesham", is_enabled=False)
    (log_id,) = await add_logs(session_factory, developer.id, "/x")

    assert (await admin_client.get(LOGS)).status_code == 200
    blocked = await admin_client.post(f"{LOGS}/{log_id}/create-rule")
    assert (blocked.status_code, blocked.json()["code"]) == (403, "developer_disabled")
