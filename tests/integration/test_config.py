import pytest

from backend.api.config import Settings


def test_settings_defaults_when_env_is_empty(monkeypatch):
    for name in (
        "WORKSPACE_ROOT",
        "DATABASE_PATH",
        "AGENT_IMPL",
        "GENERATOR_IMPL",
        "CORS_ORIGINS",
        "REQUIRE_IDEMPOTENCY_KEY",
        "API_RATE_LIMIT_PER_MINUTE",
        "APPROVAL_TTL_SECONDS",
        "COMMAND_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env() == Settings()


def test_settings_are_read_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example ,")
    monkeypatch.setenv("REQUIRE_IDEMPOTENCY_KEY", "true")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("APPROVAL_TTL_SECONDS", "60")
    monkeypatch.setenv("COMMAND_TIMEOUT_SECONDS", "10")

    settings = Settings.from_env()

    assert settings.workspace_root == tmp_path
    assert settings.database_path == tmp_path / "x.db"
    assert settings.cors_origins == ("http://a.example", "http://b.example")
    assert settings.require_idempotency_key is True
    assert (settings.rate_limit_per_minute, settings.approval_ttl_seconds) == (5, 60)
    assert settings.command_timeout_seconds == 10


def test_a_non_numeric_limit_fails_loudly_at_startup(monkeypatch):
    monkeypatch.setenv("APPROVAL_TTL_SECONDS", "soon")
    with pytest.raises(ValueError, match="APPROVAL_TTL_SECONDS"):
        Settings.from_env()
