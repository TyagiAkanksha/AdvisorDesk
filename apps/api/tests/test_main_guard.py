"""Pins `app/main.py`'s boot-time fail-fast guard (phase-2 task-01 review round 1, finding I1;
policy narrowed in review round 2).

`app/main.py` runs module-level code on import: build `Settings()`, then
unconditionally require `DATABASE_URL`/`SESSION_SECRET` to be non-empty, and
additionally require `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`GOOGLE_REDIRECT_URI` to be non-empty whenever `not settings.is_dev` (i.e.
`ENVIRONMENT=production`), before wiring a real engine + OAuth client.
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
import sys
from types import ModuleType

import pytest

_VALID_ENV = {
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/advisordesk_dummy",
    "SESSION_SECRET": "test-session-secret",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_REDIRECT_URI": "https://example.com/api/v1/auth/callback",
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
    (every `GOOGLE_*` var empty) must import cleanly — this is
    `.env.example`'s and the README's documented offline local-db path
    (`cp .env.example .env`, set `DATABASE_URL`,
    `docker compose --profile local-db up`), which round 1's unconditional
    five-guard policy broke by crash-looping the api container.
    """
    main_module = _reload_main(
        monkeypatch,
        {
            "ENVIRONMENT": "development",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "GOOGLE_REDIRECT_URI": "",
        },
    )

    assert main_module.app.title == "AdvisorDesk API"
