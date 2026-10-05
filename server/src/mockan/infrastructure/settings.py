"""`MockanSettings`: every `MOCKAN_*` variable (arch §12.3); the only place that reads the env."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MockanSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOCKAN_", env_file=".env", extra="ignore")

    # --- both processes ---
    database_url: str = "postgresql+asyncpg://mockan:mockan@localhost:5432/mockan"
    allowed_upstream_hosts: list[str] = Field(default_factory=list)  # `*.` wildcard allowed
    public_base_url: str = "https://mock.novin-tools.com"
    default_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:*", "http://127.0.0.1:*"]
    )
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    # Observability (PR-17, arch §12.2). Metrics always exist in-process; `otel_endpoint` (an
    # OTLP/HTTP collector, e.g. `http://collector:4318`) makes both processes export them. Tracing
    # is opt-in: it continues the caller's trace and sends upstreams a child `traceparent`.
    otel_endpoint: str = ""
    otel_export_interval_seconds: int = Field(default=30, ge=1)
    tracing_enabled: bool = False

    # --- admin ---
    auth_mode: Literal["oidc", "dev"] = "oidc"  # `dev` is for local use only (G-9)
    oidc_issuer: str = ""  # TODO(OQ-04): generic OIDC; provider specifics undecided
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    session_secret: str = ""
    admin_sso_subjects: list[str] = Field(default_factory=list)
    migrate_on_startup: bool = False
    panel_base_path: str = "/"  # TODO(OQ-03): where the Panel is served from

    # --- gateway ---
    snapshot_reload_seconds: int = Field(default=60, ge=1)
    snapshot_debounce_ms: int = Field(default=200, ge=0)
    # Request log (PR-12, D-18): a bounded queue (full = drop and count), a batch writer, retention.
    request_log_queue_size: int = Field(default=10_000, ge=1)
    request_log_batch_size: int = Field(default=200, ge=1)
    request_log_flush_ms: int = Field(default=500, ge=1)
    request_log_retention_days: int = Field(default=7, ge=1)
    request_log_max_rows_per_developer: int = Field(default=5_000, ge=1)
    request_log_cleanup_seconds: int = Field(default=600, ge=1)

    @property
    def database_dsn(self) -> str:
        """The URL in plain `postgresql://` form, for talking to asyncpg directly (LISTEN)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
