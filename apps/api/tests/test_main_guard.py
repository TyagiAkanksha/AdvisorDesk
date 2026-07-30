"""Pins `app/main.py`'s boot-time fail-fast guard (phase-2 task-01 review round 1, finding I1).

`app/main.py` runs module-level code on import: build `Settings()`, then
require `DATABASE_URL`/`SESSION_SECRET`/`GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI` to all be non-empty before
wiring a real engine + OAuth client. `Settings()`/`create_app()` themselves
stay zero-env-var constructible (CONVENTIONS.md §5) — this guard is
`app.main`-only, so these tests import `app.main` fresh (never cached in
`sys.modules`) under a fully controlled environment for each case, exactly
as CONVENTIONS.md §10 asks: no test previously existed for the pre-existing
`DATABASE_URL` guard, so this file covers it alongside the four new guards.

Deliberately DB-less: `make_engine()` (`app.db`) only builds a SQLAlchemy
`Engine` object (lazy — no connection attempt), so a syntactically valid but
unreachable `DATABASE_URL` is enough to exercise the "all guards pass, the
module finishes importing" case without a real database.
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
    changes) specific ones — so each test controls exactly one variable
    without depending on (or being tripped up by) whatever the ambient
    shell/`.env` happens to export.

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
        ("GOOGLE_CLIENT_ID", "google_client_id"),
        ("GOOGLE_CLIENT_SECRET", "google_client_secret"),
        ("GOOGLE_REDIRECT_URI", "google_redirect_uri"),
    ],
)
def test_main_raises_runtime_error_when_required_var_is_empty(
    monkeypatch: pytest.MonkeyPatch, blank_var: str, settings_attr: str
) -> None:
    """Each of the five required vars, blanked alone, fails `app.main` import with its own name."""
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {blank_var: ""})

    message = str(exc_info.value)
    assert blank_var in message
    assert settings_attr in message


def test_main_imports_cleanly_when_all_required_vars_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The happy path: all five vars non-empty ⇒ `app.main` builds a real `FastAPI` app."""
    main_module = _reload_main(monkeypatch, {})

    assert main_module.app.title == "AdvisorDesk API"
