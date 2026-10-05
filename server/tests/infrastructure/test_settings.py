import pytest

from mockan.infrastructure.settings import MockanSettings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in [n for n in os.environ if n.startswith("MOCKAN_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir("/")  # no stray .env


def test_defaults_match_the_architecture() -> None:
    settings = MockanSettings()
    assert settings.snapshot_reload_seconds == 60
    assert settings.snapshot_debounce_ms == 200
    assert settings.auth_mode == "oidc"
    assert settings.panel_base_path == "/"
    assert settings.log_format == "json"
    assert settings.migrate_on_startup is False
    assert settings.default_allowed_origins == ["http://localhost:*", "http://127.0.0.1:*"]


def test_variables_use_the_mockan_prefix_and_json_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MOCKAN_ALLOWED_UPSTREAM_HOSTS", '["identity.stage.internal","*.dev.internal"]'
    )
    monkeypatch.setenv("MOCKAN_AUTH_MODE", "dev")
    monkeypatch.setenv("MOCKAN_MIGRATE_ON_STARTUP", "true")
    monkeypatch.setenv("MOCKAN_SNAPSHOT_DEBOUNCE_MS", "50")
    monkeypatch.setenv("MOCKAN_ADMIN_SSO_SUBJECTS", '["abc"]')
    settings = MockanSettings()
    assert settings.allowed_upstream_hosts == ["identity.stage.internal", "*.dev.internal"]
    assert settings.auth_mode == "dev"
    assert settings.migrate_on_startup is True
    assert settings.snapshot_debounce_ms == 50
    assert settings.admin_sso_subjects == ["abc"]


def test_invalid_values_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCKAN_AUTH_MODE", "magic")
    with pytest.raises(ValueError, match="auth_mode"):
        MockanSettings()


def test_database_dsn_drops_the_driver_for_direct_asyncpg_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOCKAN_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/mockan")
    assert MockanSettings().database_dsn == "postgresql://u:p@db:5432/mockan"
