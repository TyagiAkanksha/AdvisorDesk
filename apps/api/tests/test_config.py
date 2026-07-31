"""Pins `Settings` defaults against PRD §9 and the `CORS_ORIGINS` parsing trap.

Deliberately DB-less (CONVENTIONS.md §10): nothing here touches a database.
"""

from __future__ import annotations

import pytest

from app.config import Settings

# The full PRD §9 env roster — stripped before each defaults assertion so a
# developer's ambient shell exports can never leak into the "empty env"
# scenario these tests are pinning.
_ENV_ROSTER = [
    "NVIDIA_API_KEY",
    "LLM_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "DATABASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "SESSION_SECRET",
    "ENVIRONMENT",
    "ADMIN_EMAILS",
    "CORS_ORIGINS",
    "SIMILARITY_THRESHOLD",
    "RATE_LIMIT_PER_MIN",
    "RATE_LIMIT_PER_DAY",
    "SESSION_CREATE_PER_DAY",
    "MCP_HTTP_ENABLED",
]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the §9 roster from the environment so `Settings()` reflects only its defaults."""
    for name in _ENV_ROSTER:
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_prd_with_empty_env(clean_env: None) -> None:
    """PRD §9: `Settings()` must succeed with zero env vars and match the documented defaults."""
    settings = Settings()

    # SecretStr fields (phase-2 task-01 Settings hardening; `database_url`
    # added by the phase-2 final review, finding C-5): compare the
    # unwrapped plaintext, never the SecretStr instance itself.
    assert settings.database_url.get_secret_value() == ""
    assert settings.nvidia_api_key.get_secret_value() == ""
    assert settings.llm_base_url == "https://integrate.api.nvidia.com/v1"
    assert settings.embedding_model == "nvidia/nv-embedqa-e5-v5"
    assert settings.embedding_dimensions == 1024
    assert settings.google_client_id == ""
    assert settings.google_client_secret.get_secret_value() == ""
    assert settings.google_redirect_uri == ""
    assert settings.session_secret.get_secret_value() == ""
    assert settings.environment == "development"
    assert settings.is_dev is True
    assert settings.admin_emails == ""
    assert settings.admin_email_set == set()
    assert settings.cors_origins == ""
    assert settings.cors_origin_list == []
    assert settings.similarity_threshold == 0.35
    assert settings.rate_limit_per_min == 10
    assert settings.rate_limit_per_day == 50
    assert settings.session_create_per_day == 20
    assert settings.mcp_http_enabled is False


def test_cors_origins_parses_comma_separated_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRD §9 CORS: `cors_origins` stays a plain string field (pydantic-settings JSON-decodes

    `list[str]` fields from env and raises on a bare comma-separated string) — the parsed
    allowlist is exposed through the `cors_origin_list` property instead.
    """
    monkeypatch.setenv("CORS_ORIGINS", "http://a,http://b")

    settings = Settings()

    assert settings.cors_origins == "http://a,http://b"
    assert settings.cors_origin_list == ["http://a", "http://b"]


def test_cors_origin_list_strips_whitespace_and_drops_empties(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defensive parsing: stray whitespace and trailing commas never produce blank origins."""
    monkeypatch.setenv("CORS_ORIGINS", " http://a , http://b ,")

    settings = Settings()

    assert settings.cors_origin_list == ["http://a", "http://b"]


def test_admin_email_set_is_case_insensitive_and_trims_whitespace(clean_env: None) -> None:
    """PRD §5.1/§9: the `ADMIN_EMAILS` allowlist compares case-insensitively (task-01)."""
    settings = Settings(admin_emails=" Admin@Example.com , second@example.com ,")

    assert settings.admin_email_set == {"admin@example.com", "second@example.com"}


def test_is_dev_false_only_when_environment_is_production(clean_env: None) -> None:
    """Task-01 brief ("Secure when not dev"): only an explicit "production" flips `is_dev`."""
    assert Settings(environment="production").is_dev is False
    assert Settings(environment="Production").is_dev is False
    assert Settings(environment="staging").is_dev is True
    assert Settings().is_dev is True


def test_settings_repr_hides_database_url(clean_env: None) -> None:
    """Final review, finding C-5: `database_url` is `SecretStr` — a Postgres DSN embeds the
    connection password (e.g. `postgresql://user:pw@host/db`), so a naive `repr(Settings(...))`
    (e.g. via structured logging) must never leak it, same as the other secret fields
    (`tests/test_auth_endpoints.py::test_settings_repr_hides_secret_values`, pinned, covers
    those; this extends the same pin to `database_url` specifically).
    """
    settings = Settings(
        database_url="postgresql://admin:s3cr3t-password@db.example.com/advisordesk"
    )

    rendered = repr(settings)

    assert "s3cr3t-password" not in rendered
    assert settings.database_url.get_secret_value() == (
        "postgresql://admin:s3cr3t-password@db.example.com/advisordesk"
    )
