"""Metrics, trace ids in logs and optional tracing (PR-17, arch §12.2)."""

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import structlog
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mockan.domain.enums import MatchType
from mockan.gateway.app import create_app
from mockan.infrastructure.logging import add_trace_id, configure_logging
from mockan.infrastructure.telemetry import Telemetry, current_trace_id, make_tracer_provider
from mockan.matching.snapshot import RuleSnapshotProvider
from tests.gateway.conftest import FakeUpstream, make_settings
from tests.support.live_server import LiveServer
from tests.support.snapshot_builder import SnapshotBuilder

pytestmark = [pytest.mark.asyncio, pytest.mark.req("PR-17")]


@dataclass
class Observed:
    client: httpx.AsyncClient
    reader: InMemoryMetricReader
    app: Any

    def points(self, name: str) -> list[Any]:
        found: list[Any] = []
        data = self.reader.get_metrics_data()
        for resource in data.resource_metrics if data else []:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    if metric.name == name:
                        found.extend(metric.data.data_points)
        return found

    def requests_by_source(self) -> dict[str, int]:
        return {p.attributes["source"]: int(p.value) for p in self.points("mockan_requests_total")}


ObservedFactory = Callable[..., Observed]


@pytest.fixture
async def observed(fake_upstream: FakeUpstream) -> AsyncIterator[ObservedFactory]:
    started: list[tuple[LiveServer, httpx.AsyncClient]] = []

    def make(builder: SnapshotBuilder, **extra: Any) -> Observed:
        settings = make_settings(allowed_upstream_hosts=[fake_upstream.host])
        reader = InMemoryMetricReader()
        telemetry = Telemetry("mockan-gateway", settings, readers=[reader])
        app = create_app(settings, RuleSnapshotProvider(builder.build()), telemetry, **extra)
        server = LiveServer(app).start()
        client = httpx.AsyncClient(base_url=server.url, trust_env=False, timeout=30)
        started.append((server, client))
        return Observed(client, reader, app)

    yield make
    for server, client in started:
        await client.aclose()
        server.stop()


def catalog(builder: SnapshotBuilder, upstream: FakeUpstream) -> None:
    dev = builder.developer("ehtesham")
    builder.service("echo", "/echo", environments={"stage": upstream.url})  # type: ignore[dict-item]
    builder.rule(dev, MatchType.EXACT, "/mocked")


async def test_requests_are_counted_by_source(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    catalog(snapshot_builder, fake_upstream)
    gateway = observed(snapshot_builder)

    await gateway.client.get("/ehtesham/mocked")
    await gateway.client.get("/ehtesham/mocked")
    await gateway.client.get("/ehtesham/echo")
    await gateway.client.get("/ehtesham/unregistered")  # service_not_resolved
    await gateway.client.get("/nobody/x")  # developer_not_found
    await gateway.client.get("/_mockan/health/live")  # not a request to count

    assert gateway.requests_by_source() == {"mock": 2, "proxy": 1, "error": 2}


async def test_only_proxied_requests_feed_the_proxy_duration(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    catalog(snapshot_builder, fake_upstream)
    gateway = observed(snapshot_builder)

    await gateway.client.get("/ehtesham/mocked")
    await gateway.client.get("/ehtesham/echo")
    await gateway.client.get("/ehtesham/echo")

    (histogram,) = gateway.points("mockan_proxy_duration_ms")
    assert histogram.count == 2
    assert 0 < histogram.sum < 10_000  # milliseconds


async def test_a_streaming_proxied_response_is_timed_to_the_end_of_the_stream(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    del dev
    snapshot_builder.service("sse", "/sse", environments={"stage": fake_upstream.url})  # type: ignore[dict-item]
    gateway = observed(snapshot_builder)

    await gateway.client.get("/ehtesham/sse", params={"count": 3, "interval": 0.1})

    (histogram,) = gateway.points("mockan_proxy_duration_ms")
    assert histogram.sum >= 200  # three events 100 ms apart


async def test_the_snapshot_age_and_dropped_entries_are_observed(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham")
    gateway = observed(snapshot_builder)
    assert gateway.points("mockan_snapshot_age_seconds") == []  # no SnapshotService in this app

    class FakeService:
        age_seconds = 12.5

    gateway.app.state.snapshot_service = FakeService()
    gateway.app.state.request_log.dropped = 4

    assert [p.value for p in gateway.points("mockan_snapshot_age_seconds")] == [12.5]
    assert [p.value for p in gateway.points("mockan_request_log_dropped_total")] == [4]


async def test_the_age_is_not_reported_before_the_first_snapshot_loads(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder
) -> None:
    snapshot_builder.developer("ehtesham")
    gateway = observed(snapshot_builder)

    class Starting:
        age_seconds = None

    gateway.app.state.snapshot_service = Starting()

    assert gateway.points("mockan_snapshot_age_seconds") == []


# ---- logs ----------------------------------------------------------------------------------


def test_trace_id_is_added_inside_a_span_and_absent_outside() -> None:
    tracer = make_tracer_provider("test", make_settings()).get_tracer("t")

    assert current_trace_id() is None
    assert "trace_id" not in add_trace_id(None, "info", {})
    with tracer.start_as_current_span("work") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        assert current_trace_id() == expected
        assert add_trace_id(None, "info", {"event": "x"}) == {"event": "x", "trace_id": expected}


def test_json_log_lines_carry_the_trace_id_and_the_bound_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")
    tracer = make_tracer_provider("test", make_settings()).get_tracer("t")

    with tracer.start_as_current_span("work") as span:
        structlog.contextvars.bind_contextvars(
            developer="ehtesham", service="limsa", source="mock", rule_id="r-1"
        )
        structlog.get_logger().info("something_happened", detail="x")
        trace_id = format(span.get_span_context().trace_id, "032x")
    structlog.contextvars.clear_contextvars()

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["trace_id"] == trace_id
    assert (line["developer"], line["service"], line["source"], line["rule_id"]) == (
        "ehtesham",
        "limsa",
        "mock",
        "r-1",
    )


async def test_gateway_logs_name_the_source_and_rule_of_a_request(
    observed: ObservedFactory,
    snapshot_builder: SnapshotBuilder,
    fake_upstream: FakeUpstream,
    capfd: pytest.CaptureFixture[str],
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.rule(
        dev, MatchType.EXACT, "/tpl", body="{{ route.nope }}", body_mode=_template()
    )
    gateway = observed(snapshot_builder)
    async with gateway.app.router.lifespan_context(gateway.app):  # configures structlog (JSON)
        await gateway.client.get("/ehtesham/tpl")

    out = capfd.readouterr().out
    failed = [json.loads(line) for line in out.splitlines() if "mock_render_failed" in line]
    assert failed
    assert (failed[0]["developer"], failed[0]["source"]) == ("ehtesham", "mock")
    assert failed[0]["rule_id"]


def _template() -> Any:
    from mockan.domain.enums import BodyMode

    return BodyMode.TEMPLATE


# ---- tracing (opt-in) ----------------------------------------------------------------------


async def test_with_tracing_on_the_trace_continues_and_upstreams_get_a_child_traceparent(
    snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    catalog(snapshot_builder, fake_upstream)
    exporter = InMemorySpanExporter()
    settings = make_settings(allowed_upstream_hosts=[fake_upstream.host], tracing_enabled=True)
    provider = make_tracer_provider("mockan-gateway", settings)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = create_app(
        settings, RuleSnapshotProvider(snapshot_builder.build()), tracer_provider=provider
    )
    server = LiveServer(app).start()
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    parent = f"00-{trace_id}-b7ad6b7169203331-01"
    try:
        async with httpx.AsyncClient(base_url=server.url, trust_env=False) as client:
            response = await client.get("/ehtesham/echo", headers={"traceparent": parent})
            await client.get("/_mockan/health/live")
    finally:
        server.stop()

    seen = {k.lower(): v for k, v in response.json()["headers"]}["traceparent"]
    version, upstream_trace, span_id, flags = seen.split("-")
    assert (version, upstream_trace, flags) == ("00", trace_id, "01")  # same trace...
    assert span_id != "b7ad6b7169203331"  # ...a child of the Gateway's own span
    spans = exporter.get_finished_spans()
    assert {format(s.context.trace_id, "032x") for s in spans} == {trace_id}
    assert not any("health" in (s.name + str(s.attributes)) for s in spans)  # health isn't traced
    assert trace.get_tracer_provider() is not provider  # nothing global was touched


async def test_with_tracing_off_the_clients_traceparent_goes_upstream_untouched(
    observed: ObservedFactory, snapshot_builder: SnapshotBuilder, fake_upstream: FakeUpstream
) -> None:
    catalog(snapshot_builder, fake_upstream)
    gateway = observed(snapshot_builder)
    parent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    response = await gateway.client.get("/ehtesham/echo", headers={"traceparent": parent})

    assert {k.lower(): v for k, v in response.json()["headers"]}["traceparent"] == parent
