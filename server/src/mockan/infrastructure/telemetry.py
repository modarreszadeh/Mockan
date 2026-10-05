"""Metrics and tracing (PR-17, arch §12.2): OpenTelemetry, off the request path.

Metric names (architecture §12.2):

* `mockan_requests_total{source}`: Gateway responses by `mock`, `proxy` or `error`;
* `mockan_proxy_duration_ms`: how long proxied requests take, Gateway overhead included;
* `mockan_snapshot_age_seconds`: seconds since the rule snapshot was last brought up to date;
* `mockan_request_log_dropped_total`: request-log entries dropped (full queue or failed insert).

A `Telemetry` owns its own `MeterProvider`, so tests can read it with an in-memory reader and
two apps in one process don't share state. With `MOCKAN_OTEL_ENDPOINT` set it also exports to an
OTLP/HTTP collector.
"""

from collections.abc import Callable, Iterable, Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from mockan.infrastructure.settings import MockanSettings

# Proxied requests are mostly fast, but an upstream can take seconds.
_DURATION_BUCKETS = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000]


class Telemetry:
    def __init__(
        self,
        service_name: str,
        settings: MockanSettings,
        *,
        readers: Sequence[MetricReader] = (),
    ) -> None:
        self.service_name = service_name
        self._resource = Resource.create({"service.name": service_name})
        all_readers = list(readers)
        if settings.otel_endpoint:
            all_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=_signal_url(settings.otel_endpoint, "metrics")),
                    export_interval_millis=settings.otel_export_interval_seconds * 1000,
                )
            )
        self.provider = MeterProvider(resource=self._resource, metric_readers=all_readers)
        meter = self.provider.get_meter("mockan")
        self.requests = meter.create_counter(
            "mockan_requests_total", unit="1", description="Gateway responses by source"
        )
        self.proxy_duration = meter.create_histogram(
            "mockan_proxy_duration_ms",
            unit="ms",
            description="Duration of proxied requests, Gateway overhead included",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        )
        self._meter = meter

    def observe_snapshot_age(self, read: Callable[[], float | None]) -> None:
        def callback(_options: CallbackOptions) -> Iterable[Observation]:
            age = read()
            return [] if age is None else [Observation(age)]

        self._meter.create_observable_gauge(
            "mockan_snapshot_age_seconds",
            callbacks=[callback],
            unit="s",
            description="Seconds since the rule snapshot was last brought up to date",
        )

    def observe_request_log_dropped(self, read: Callable[[], int]) -> None:
        def callback(_options: CallbackOptions) -> Iterable[Observation]:
            return [Observation(read())]

        self._meter.create_observable_counter(
            "mockan_request_log_dropped_total",
            callbacks=[callback],
            unit="1",
            description="Request-log entries dropped (queue full or insert failed)",
        )

    def tracer_provider(
        self, settings: MockanSettings, exporter: SpanExporter | None = None
    ) -> TracerProvider:
        return make_tracer_provider(self.service_name, settings, exporter)

    def shutdown(self) -> None:
        self.provider.shutdown()


def make_tracer_provider(
    service_name: str, settings: MockanSettings, exporter: SpanExporter | None = None
) -> TracerProvider:
    """A tracer provider for one service; spans are exported to `exporter` or the OTLP endpoint."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif settings.otel_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=_signal_url(settings.otel_endpoint, "traces"))
            )
        )
    return provider


def _signal_url(endpoint: str, signal: str) -> str:
    return f"{endpoint.rstrip('/')}/v1/{signal}"


def current_trace_id() -> str | None:
    """The active span's trace id as 32 hex characters, for log lines; `None` outside a span."""
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None
