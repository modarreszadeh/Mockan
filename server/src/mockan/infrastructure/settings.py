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

    @property
    def database_dsn(self) -> str:
        """The URL in plain `postgresql://` form, for talking to asyncpg directly (LISTEN)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
