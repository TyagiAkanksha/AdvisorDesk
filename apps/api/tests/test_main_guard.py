"""Pins `app/main.py`'s boot-time fail-fast guard (phase-2 task-01 review round 1, finding I1;
policy narrowed in review round 2; `NVIDIA_API_KEY` joined the not-`is_dev` list in phase-3
task-02).

`app/main.py` runs module-level code on import: build `Settings()`, then
unconditionally require `DATABASE_URL`/`SESSION_SECRET` to be non-empty, and
additionally require `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`GOOGLE_REDIRECT_URI`/`ADMIN_EMAILS`/`NVIDIA_API_KEY` to be non-empty
whenever `not settings.is_dev` (i.e. `ENVIRONMENT=production`), before
wiring a real engine + OAuth client + embedding pipeline.
`Settings()`/`create_app()` themselves stay zero-env-var constructible
(CONVENTIONS.md §5) — this guard is `app.main`-only, so these tests import
`app.main` fresh (never cached in `sys.modules`) under a fully controlled
environment for each case, exactly as CONVENTIONS.md §10 asks.

Review round 2: round 1 pinned all five guards as unconditional, which broke
the documented offline dev path — `.env.example` ships the three `GOOGLE_*`
vars empty, and Google credentials are unobtainable offline by definition,
so a fresh `cp .env.example .env` + local-db boot crash-looped the api
container. This file now pins the corrected policy: `database_url` and
`session_secret` fire regardless of environment; each `GOOGLE_*` guard fires
only with `ENVIRONMENT=production`; and — the regression-catching case that
round 1 lacked — `app.main` imports cleanly in development with ONLY
`DATABASE_URL`/`SESSION_SECRET` set and every `GOOGLE_*` var empty.

Deliberately DB-less: `make_engine()` (`app.db`) only builds a SQLAlchemy
`Engine` object (lazy — no connection attempt), so a syntactically valid but
unreachable `DATABASE_URL` is enough to exercise the "all guards pass, the
module finishes importing" cases without a real database.
"""

from __future__ import annotations

import importlib
import logging
import sys
from types import ModuleType

import pytest

_VALID_ENV = {
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/advisordesk_dummy",
    "SESSION_SECRET": "test-session-secret",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_REDIRECT_URI": "https://example.com/api/v1/auth/callback",
    # Final review, finding C-6: ADMIN_EMAILS joined the not-is_dev required
    # list below, same dev-exempt/production-required shape as the three
    # GOOGLE_* vars above.
    "ADMIN_EMAILS": "admin@example.com",
    # Phase-3 task-02: NVIDIA_API_KEY joined the not-is_dev required list
    # below, same dev-exempt/production-required shape.
    "NVIDIA_API_KEY": "test-nvidia-api-key",
}


def _reload_main(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]) -> ModuleType:
    """(Re-)import `app.main` under `_VALID_ENV` with `overrides` applied on top.

    Every guarded var is set to a valid value, then `overrides` blanks (or
    changes) specific ones — so each test controls exactly the variable(s)
    under test without depending on (or being tripped up by) whatever the
    ambient shell/`.env` happens to export.

    Always pops `app.main` from `sys.modules` first so its module-level
    guard code actually re-runs (a plain `import` would return the
    already-imported, cached module).
    """
    env = {**_VALID_ENV, **overrides}
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main")


@pytest.mark.parametrize(
    ("blank_var", "settings_attr"),
    [
        ("DATABASE_URL", "database_url"),
        ("SESSION_SECRET", "session_secret"),
    ],
)
def test_unconditional_guard_raises_regardless_of_environment(
    monkeypatch: pytest.MonkeyPatch, blank_var: str, settings_attr: str
) -> None:
    """`DATABASE_URL`/`SESSION_SECRET`, blanked alone, fail in BOTH dev and production.

    An empty/known session-signing key (or no database) is fail-open and
    never allowed — unlike the three `GOOGLE_*` guards below, environment
    never exempts these two.
    """
    for environment in ("development", "production"):
        with pytest.raises(RuntimeError) as exc_info:
            _reload_main(monkeypatch, {blank_var: "", "ENVIRONMENT": environment})

        message = str(exc_info.value)
        assert blank_var in message
        assert settings_attr in message


@pytest.mark.parametrize(
    ("blank_var", "settings_attr"),
    [
        ("GOOGLE_CLIENT_ID", "google_client_id"),
        ("GOOGLE_CLIENT_SECRET", "google_client_secret"),
        ("GOOGLE_REDIRECT_URI", "google_redirect_uri"),
    ],
)
def test_google_guard_raises_in_production_when_blank(
    monkeypatch: pytest.MonkeyPatch, blank_var: str, settings_attr: str
) -> None:
    """Each `GOOGLE_*` var, blanked alone, fails `app.main` import under production."""
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {blank_var: "", "ENVIRONMENT": "production"})

    message = str(exc_info.value)
    assert blank_var in message
    assert settings_attr in message


@pytest.mark.parametrize(
    "blank_var",
    ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
)
def test_google_guard_does_not_raise_in_development_when_blank(
    monkeypatch: pytest.MonkeyPatch, blank_var: str
) -> None:
    """Each `GOOGLE_*` var, blanked alone, is exempt under dev (`ENVIRONMENT` unset/non-production).

    The offline dev path never has real Google credentials available —
    admin login just won't work until they're set; the app must still boot.
    """
    main_module = _reload_main(monkeypatch, {blank_var: "", "ENVIRONMENT": "development"})

    assert main_module.app.title == "AdvisorDesk API"


def test_main_imports_cleanly_when_all_required_vars_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The happy path: all five vars non-empty ⇒ `app.main` builds a real `FastAPI` app."""
    main_module = _reload_main(monkeypatch, {"ENVIRONMENT": "production"})

    assert main_module.app.title == "AdvisorDesk API"


def test_main_imports_cleanly_in_dev_with_only_database_url_and_session_secret_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The offline-dev boot pin: this is the exact case round 1's guard broke.

    `ENVIRONMENT=development` + only `DATABASE_URL`/`SESSION_SECRET` set
    (every `GOOGLE_*` var AND `NVIDIA_API_KEY` empty) must import cleanly —
    this is `.env.example`'s and the README's documented offline local-db
    path (`cp .env.example .env`, set `DATABASE_URL`,
    `docker compose --profile local-db up`), which round 1's unconditional
    five-guard policy broke by crash-looping the api container. Also pins
    phase-3 task-02's real embedder-client boot-safety fix
    (`app.rag.embeddings`'s `from_settings` constructor): building the
    `openai` SDK client with a blank API key must not itself raise, since
    `NVIDIA_API_KEY` is dev-exempt same as the `GOOGLE_*` vars.
    """
    main_module = _reload_main(
        monkeypatch,
        {
            "ENVIRONMENT": "development",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "GOOGLE_REDIRECT_URI": "",
            "NVIDIA_API_KEY": "",
        },
    )

    assert main_module.app.title == "AdvisorDesk API"


# ---------------------------------------------------------------------------
# Final review, finding C-6: ADMIN_EMAILS joins the not-is_dev required list
# ---------------------------------------------------------------------------


def test_admin_emails_guard_raises_in_production_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ADMIN_EMAILS`, blanked alone, fails `app.main` import under production.

    An empty `ADMIN_EMAILS` in production boots cleanly but locks EVERY
    Google identity out of `/auth/callback` (`ForbiddenError` on every
    login attempt, PRD §5.1) — no admin could ever sign in, silently.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {"ADMIN_EMAILS": "", "ENVIRONMENT": "production"})

    message = str(exc_info.value)
    assert "ADMIN_EMAILS" in message
    assert "admin_emails" in message


def test_admin_emails_guard_does_not_raise_in_development_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ADMIN_EMAILS`, blanked alone, is exempt under dev — same shape as the `GOOGLE_*` guards.

    The offline dev path never has real admin emails configured either;
    admin login just won't work until `ADMIN_EMAILS` is set, but the app
    must still boot.
    """
    main_module = _reload_main(monkeypatch, {"ADMIN_EMAILS": "", "ENVIRONMENT": "development"})

    assert main_module.app.title == "AdvisorDesk API"


# ---------------------------------------------------------------------------
# Phase-3 task-02: NVIDIA_API_KEY joins the not-is_dev required list
# ---------------------------------------------------------------------------


def test_nvidia_api_key_guard_raises_in_production_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`NVIDIA_API_KEY`, blanked alone, fails `app.main` import under production.

    An empty `NVIDIA_API_KEY` in production boots cleanly but every
    publish/edit-of-published call fails at the first real embedding
    request instead — never until an admin actually tries to publish, which
    is worse than failing fast at boot.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {"NVIDIA_API_KEY": "", "ENVIRONMENT": "production"})

    message = str(exc_info.value)
    assert "NVIDIA_API_KEY" in message
    assert "nvidia_api_key" in message


def test_nvidia_api_key_guard_does_not_raise_in_development_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`NVIDIA_API_KEY`, blanked alone, is exempt under dev — same shape as the `GOOGLE_*` guards.

    The offline dev path never has a real NVIDIA key configured either;
    publishing just won't work until it's set, but the app must still boot
    (`app.rag.embeddings`'s real embedder client tolerates the empty value
    at construction time — see its `from_settings` docstring).
    """
    main_module = _reload_main(monkeypatch, {"NVIDIA_API_KEY": "", "ENVIRONMENT": "development"})

    assert main_module.app.title == "AdvisorDesk API"


# ---------------------------------------------------------------------------
# Final review, finding C-1/F1: CORS_ORIGINS empty -> boot-time WARNING, not a crash
# ---------------------------------------------------------------------------


def test_empty_cors_origins_logs_a_warning_but_still_boots(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`CORS_ORIGINS` unset (empty) logs a WARNING naming it, but `app.main` still imports.

    A same-origin deployment (or a reverse proxy that makes the API and its
    frontend(s) look same-origin to the browser) legitimately needs no CORS
    allowlist — so this must never be a boot-time failure, unlike
    `DATABASE_URL`/`SESSION_SECRET` above. It must still be loud, since a
    forgotten `CORS_ORIGINS` silently breaks every cross-origin admin/client
    request with no server-side signal otherwise (this exact gap shipped to
    the phase-2 final review as finding C-1).
    """
    with caplog.at_level(logging.WARNING, logger="app.main"):
        main_module = _reload_main(monkeypatch, {"CORS_ORIGINS": ""})

    assert main_module.app.title == "AdvisorDesk API"
    warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("CORS_ORIGINS" in message for message in warnings)


def test_nonempty_cors_origins_logs_no_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A non-empty `CORS_ORIGINS` produces no boot-time warning — the happy path is quiet."""
    with caplog.at_level(logging.WARNING, logger="app.main"):
        _reload_main(monkeypatch, {"CORS_ORIGINS": "http://localhost:3001"})

    assert caplog.records == []
