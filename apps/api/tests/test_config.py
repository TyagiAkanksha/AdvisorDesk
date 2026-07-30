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
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "SESSION_SECRET",
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

    assert settings.database_url == ""
    assert settings.openai_api_key == ""
    assert settings.google_client_id == ""
    assert settings.google_client_secret == ""
    assert settings.session_secret == ""
    assert settings.admin_emails == ""
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
