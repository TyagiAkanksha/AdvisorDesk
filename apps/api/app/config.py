"""Typed application settings — the single config surface (CONVENTIONS.md §7).

PRD §9 defines the full env-var roster and defaults; every later task reads
configuration through `Settings` rather than `os.environ` directly.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration sourced from environment variables (PRD §9).

    Field names are the lower-cased env-var names; pydantic-settings matches
    them case-insensitively by default, so `DATABASE_URL` populates
    `database_url` with no extra configuration.

    `Settings()` must succeed with **zero** environment variables set
    (CONVENTIONS.md §5) — this is what lets `create_app()` build a DB-less
    app for tests and the OpenAPI baseline export. `database_url` therefore
    defaults to `""` rather than being a required field; `app/main.py` is
    the only place that enforces it is non-empty before wiring a real
    engine.
    """

    openai_api_key: str = ""
    database_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    session_secret: str = ""
    admin_emails: str = ""

    # Implementation trap: pydantic-settings JSON-decodes "complex" field
    # types (list[str], dict, ...) from their env-var string BEFORE
    # validation, and raises on a bare comma-separated value like
    # "http://a,http://b" (it is not valid JSON). So this stays a plain
    # `str` field, parsed by hand via the `cors_origin_list` property below.
    cors_origins: str = ""

    similarity_threshold: float = 0.35
    rate_limit_per_min: int = 10
    rate_limit_per_day: int = 50
    session_create_per_day: int = 20
    mcp_http_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        """The `cors_origins` env value split into an allowlist (PRD §9 CORS).

        Splits on comma, strips whitespace from each entry, and drops empty
        entries (a stray trailing comma or blank env var never produces a
        blank origin).
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
