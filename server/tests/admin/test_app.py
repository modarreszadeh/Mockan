"""App wiring: the lifespan (logging, migrate on startup) and the dev-mode warning."""

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from mockan.admin.app import create_app
from mockan.infrastructure.settings import MockanSettings


def test_openapi_and_docs_live_under_api_v1(
    admin_settings: MockanSettings,
) -> None:
    app = create_app(admin_settings)

    assert app.openapi_url == "/api/v1/openapi.json"
    assert app.docs_url == "/api/v1/docs"


async def test_the_app_without_a_database_still_answers_unauthenticated_routes(
    admin_settings: MockanSettings,
) -> None:
    """No DB is touched before a session is needed: the 404 for an unknown path comes first."""
    transport = httpx.ASGITransport(app=create_app(admin_settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://admin") as client:
        response = await client.get("/")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.db
async def test_the_lifespan_migrates_an_empty_database_when_asked(
    admin_settings: MockanSettings, pg_container: str
) -> None:
    fresh = make_url(pg_container).set(database="migrate_on_startup")
    admin = create_async_engine(pg_container, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text('CREATE DATABASE "migrate_on_startup"'))
    settings = admin_settings.model_copy(
        update={
            "database_url": fresh.render_as_string(hide_password=False),
            "migrate_on_startup": True,
        }
    )
    app = create_app(settings)

    try:
        async with app.router.lifespan_context(app):
            # The app serves with the schema in place: the first login needs the tables.
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://admin") as client:
                assert (
                    await client.get("/api/v1/auth/login", params={"as": "a"})
                ).status_code == 303
    finally:
        async with admin.connect() as connection:
            await connection.execute(text('DROP DATABASE "migrate_on_startup" WITH (FORCE)'))
        await admin.dispose()


@pytest.mark.db
async def test_the_lifespan_does_not_migrate_by_default(
    admin_settings: MockanSettings, pg_container: str
) -> None:
    fresh = make_url(pg_container).set(database="no_migration")
    admin = create_async_engine(pg_container, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text('CREATE DATABASE "no_migration"'))
    settings = admin_settings.model_copy(
        update={"database_url": fresh.render_as_string(hide_password=False)}
    )
    app = create_app(settings)

    try:
        async with app.router.lifespan_context(app):
            inspected = create_async_engine(settings.database_url)
            async with inspected.connect() as connection:
                tables = await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'mockan'"
                    )
                )
            await inspected.dispose()
        assert tables == 0
    finally:
        async with admin.connect() as connection:
            await connection.execute(text('DROP DATABASE "no_migration" WITH (FORCE)'))
        await admin.dispose()


@pytest.mark.req("PR-17")
async def test_the_admin_is_traced_only_when_asked(admin_settings: MockanSettings) -> None:
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from mockan.infrastructure.telemetry import make_tracer_provider

    exporter = InMemorySpanExporter()
    settings = admin_settings.model_copy(update={"tracing_enabled": True})
    provider = make_tracer_provider("mockan-admin", settings)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    traced = create_app(settings, tracer_provider=provider)
    plain = create_app(admin_settings)

    for app in (traced, plain):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://admin"
        ) as client:
            await client.get("/api/v1/openapi.json")  # needs no database

    spans = exporter.get_finished_spans()
    assert spans and all(s.resource.attributes["service.name"] == "mockan-admin" for s in spans)
    assert len({s.context.trace_id for s in spans}) == 1  # only the traced app produced any
