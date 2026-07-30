"""Typed application settings — the single config surface (CONVENTIONS.md §7).

PRD §9 defines the full env-var roster and defaults; every later task reads
configuration through `Settings` rather than `os.environ` directly.
"""

from __future__ import annotations

from pydantic import SecretStr
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

    `openai_api_key`/`google_client_secret`/`session_secret` are `SecretStr`
    (phase-2 task-01 Settings hardening) so a naive `repr(Settings(...))` —
    e.g. via structured logging — never leaks a secret value; call sites
    read the plaintext via `.get_secret_value()`. Empty-string defaults
    become `SecretStr("")`, preserving the zero-env-vars constructibility
    guarantee above.
    """

    openai_api_key: SecretStr = SecretStr("")
    database_url: str = ""
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    admin_emails: str = ""

    # Not part of the PRD §9 env roster: the real `HttpxGoogleOAuthClient`
    # (app.auth.oauth, phase-2 task-01) needs a fixed, Google-console-
    # registered callback URL to exchange a code — this is that URL. Empty
    # by default so `Settings()`/`create_app()` stay zero-env-var
    # constructible; only a real deployment sets it.
    google_redirect_uri: str = ""

    # Also not part of the PRD §9 env roster: the minimal signal
    # `app.auth.sessions.issue_cookie` needs to decide the session cookie's
    # `Secure` flag ("Secure when not dev" — task-01 brief). Defaults to
    # `"development"` so local `docker compose up`/tests (plain HTTP) get a
    # cookie that actually round-trips; a real deployment sets
    # `ENVIRONMENT=production`.
    environment: str = "development"

    # Also not part of the PRD §9 env roster (phase-2 task-01 review M8
    # resolution, amended before task-04): the admin SPA's origin.
    # `app.routes.auth_routes.auth_callback` 303-redirects here on success
    # so the browser lands back in the admin app after Google sign-in
    # instead of dead-ending on a bodyless response on the API's own
    # origin. Defaults to the local admin dev server so
    # `Settings()`/`create_app()` stay zero-env-var constructible; a real
    # deployment sets `ADMIN_APP_URL` to the admin app's real origin.
    admin_app_url: str = "http://localhost:3001"

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

    @property
    def admin_email_set(self) -> set[str]:
        """The `ADMIN_EMAILS` allowlist, parsed once (PRD §5.1/§9).

        Comma-separated, case-insensitively compared (email local/domain
        parts are conventionally treated case-insensitively) — mirrors
        `cors_origin_list`'s parsing shape.
        """
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def is_dev(self) -> bool:
        """Whether `ENVIRONMENT` selects local-development defaults (task-01 brief).

        Anything other than `"production"` (case-insensitive) is treated as
        dev — the safer default when the var is unset entirely.
        """
        return self.environment.strip().lower() != "production"
