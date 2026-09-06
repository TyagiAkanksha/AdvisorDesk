"""Pins `app/main.py`'s boot-time fail-fast guard (phase-2 task-01 review round 1, finding I1;
policy narrowed in review round 2; a provider-selected LLM credential guard joined the
not-`is_dev` list in phase-3 task-02, made provider-aware by task 6R-15).

`app/main.py` runs module-level code on import: build `Settings()`, then
unconditionally require `DATABASE_URL`/`SESSION_SECRET` to be non-empty, and
additionally require `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`GOOGLE_REDIRECT_URI`/`ADMIN_EMAILS`/the ACTIVE `llm_provider`'s API key
(`settings.llm_api_key` — `OPENAI_API_KEY` under the default
`llm_provider="openai"`, `NVIDIA_API_KEY` under `llm_provider="nvidia"`) to
be non-empty whenever `not settings.is_dev` (i.e. `ENVIRONMENT=production`),
before wiring a real engine + OAuth client + embedding pipeline.
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

Task 6R-15 (6R-14 review, Important finding): task 6R-14 added
`Settings.llm_provider`/`openai_api_key`/`llm_api_key` and flipped the
default provider to `"openai"`, but the guard below still validated
`NVIDIA_API_KEY` unconditionally — under the new default that is wrong both
ways: a missing `OPENAI_API_KEY` booted silently, and dropping the
now-unused `NVIDIA_API_KEY` placeholder from a production env crash-looped
boot. The contract pinned below is provider-aware instead: `_VALID_ENV`'s
baseline sets `OPENAI_API_KEY` (never `NVIDIA_API_KEY` — a clean production
boot under the default provider must never need the inactive key), and the
guard is exercised under both `llm_provider` values to pin the
provider-selection symmetry.

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
    # Task 6R-15 (6R-14 review): the guard now validates the ACTIVE
    # `llm_provider`'s key, not `NVIDIA_API_KEY` unconditionally.
    # `llm_provider` defaults to `"openai"` (task 6R-14) so the baseline
    # pins that default explicitly and sets its active credential,
    # `OPENAI_API_KEY` — deliberately NOT `NVIDIA_API_KEY`: a clean
    # production boot under the default provider must never require the
    # inactive NVIDIA key (see
    # `test_main_imports_cleanly_when_all_required_vars_are_set` below).
    "LLM_PROVIDER": "openai",
    "OPENAI_API_KEY": "test-openai-api-key",
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
    """The happy path: all five vars non-empty ⇒ `app.main` builds a real `FastAPI` app.

    Task 6R-15's deploy-safety pin: `_VALID_ENV`'s baseline never sets
    `NVIDIA_API_KEY` at all, so this also proves a clean production boot
    under the default `llm_provider="openai"` never needs the inactive
    NVIDIA key present — matching a real deployment that has dropped it
    from the env entirely.
    """
    main_module = _reload_main(monkeypatch, {"ENVIRONMENT": "production"})

    assert main_module.app.title == "AdvisorDesk API"


def test_main_imports_cleanly_in_dev_with_only_database_url_and_session_secret_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The offline-dev boot pin: this is the exact case round 1's guard broke.

    `ENVIRONMENT=development` + only `DATABASE_URL`/`SESSION_SECRET` set
    (every `GOOGLE_*` var AND both LLM provider keys empty) must import
    cleanly — this is `.env.example`'s and the README's documented offline
    local-db path (`cp .env.example .env`, set `DATABASE_URL`,
    `docker compose --profile local-db up`), which round 1's unconditional
    five-guard policy broke by crash-looping the api container.
    `.env.example` ships `LLM_PROVIDER=openai` with `OPENAI_API_KEY`/
    `NVIDIA_API_KEY` both blank, so this also pins task 6R-15's
    provider-aware guard alongside phase-3 task-02's real embedder-client
    boot-safety fix (`app.rag.embeddings`'s `from_settings` constructor):
    building the `openai` SDK client with a blank API key must not itself
    raise, since both keys are dev-exempt same as the `GOOGLE_*` vars.
    """
    main_module = _reload_main(
        monkeypatch,
        {
            "ENVIRONMENT": "development",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "GOOGLE_REDIRECT_URI": "",
            "OPENAI_API_KEY": "",
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
# Task 6R-15 (6R-14 review, Important finding): the guard validates the
# ACTIVE `llm_provider`'s key (`settings.llm_api_key`), not `NVIDIA_API_KEY`
# unconditionally — a missing `OPENAI_API_KEY` under the default
# `llm_provider="openai"` must fail fast in production, the inactive
# `NVIDIA_API_KEY` must NOT be required, and `llm_provider="nvidia"` flips
# which key is active (provider-selection symmetry).
# ---------------------------------------------------------------------------


def test_openai_api_key_guard_raises_in_production_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OPENAI_API_KEY`, blanked alone, fails `app.main` import under production
    (`llm_provider` defaults to `"openai"` — this is the active provider's key).

    A missing `OPENAI_API_KEY` under the default provider boots cleanly
    today but every publish/chat/agent call fails at the first real
    embedding/completion request instead — never until an admin or client
    actually uses it, which is worse than failing fast at boot. This is the
    exact boot-safety property `NVIDIA_API_KEY` used to have unconditionally
    (phase-3 task-02), restored here for whichever provider is actually
    active.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {"OPENAI_API_KEY": "", "ENVIRONMENT": "production"})

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert "openai_api_key" in message


def test_openai_api_key_guard_does_not_raise_in_development_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OPENAI_API_KEY`, blanked alone, is exempt under dev — same shape as the `GOOGLE_*` guards.

    The offline dev path never has a real OpenAI key configured either
    (`.env.example` ships it blank); publishing/chat just won't work until
    it's set, but the app must still boot (`OpenAICompatibleEmbedder`/
    `OpenAICompatibleChatLLM`/`OpenAICompatibleAgentLLM`'s `from_settings`
    all tolerate the empty value at construction time).
    """
    main_module = _reload_main(monkeypatch, {"OPENAI_API_KEY": "", "ENVIRONMENT": "development"})

    assert main_module.app.title == "AdvisorDesk API"


def test_inactive_nvidia_api_key_does_not_raise_in_production_under_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under `llm_provider="openai"` (the default), a blank/absent `NVIDIA_API_KEY` must NOT
    raise in production.

    This is the exact deploy-safety property task 6R-15 fixes: before this
    fix, dropping the now-unused `NVIDIA_API_KEY` placeholder from a
    production env crash-looped boot even though nothing reads it under the
    OpenAI provider. `NVIDIA_API_KEY` is absent from `_VALID_ENV` entirely
    (never set by `_reload_main`), so this also covers the "var dropped from
    the env altogether" scenario, not just "set to an empty string".
    """
    main_module = _reload_main(monkeypatch, {"LLM_PROVIDER": "openai", "ENVIRONMENT": "production"})

    assert main_module.app.title == "AdvisorDesk API"


def test_nvidia_api_key_guard_raises_in_production_when_blank_under_nvidia_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under `llm_provider="nvidia"`, a blank `NVIDIA_API_KEY` DOES raise in production.

    The provider-selection mirror image of the `openai` case above:
    whichever provider is active, ITS key is required at boot.
    """
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(
            monkeypatch,
            {"LLM_PROVIDER": "nvidia", "NVIDIA_API_KEY": "", "ENVIRONMENT": "production"},
        )

    message = str(exc_info.value)
    assert "NVIDIA_API_KEY" in message
    assert "nvidia_api_key" in message


def test_inactive_openai_api_key_does_not_raise_in_production_under_nvidia_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under `llm_provider="nvidia"`, a blank `OPENAI_API_KEY` must NOT raise in production.

    It's the inactive provider's key. Pins the full provider-selection
    symmetry alongside the three tests above: exactly one of
    `OPENAI_API_KEY`/`NVIDIA_API_KEY` is required at a time, selected by
    `llm_provider`.
    """
    main_module = _reload_main(
        monkeypatch,
        {
            "LLM_PROVIDER": "nvidia",
            "NVIDIA_API_KEY": "test-nvidia-api-key",
            "OPENAI_API_KEY": "",
            "ENVIRONMENT": "production",
        },
    )

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


# ---------------------------------------------------------------------------
# Phase-3 task-02 review round 1, finding M3: settings.embedding_dimensions
# must match Chunk.embedding's actual pgvector column width, asserted at boot
# ---------------------------------------------------------------------------


def test_mismatched_embedding_dimensions_fails_boot_naming_both_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`EMBEDDING_DIMENSIONS` drifting from `Chunk.embedding`'s 1024-dim column fails fast at
    boot, naming both numbers, instead of booting cleanly and only surfacing as a
    dimension-mismatch `EmbeddingFailedError` on the first real publish (a config/schema drift
    that's cheap to catch at import time and expensive to catch at request time).
    """
    with pytest.raises(RuntimeError) as exc_info:
        _reload_main(monkeypatch, {"EMBEDDING_DIMENSIONS": "768"})

    message = str(exc_info.value)
    assert "768" in message
    assert "1024" in message


def test_matching_embedding_dimensions_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`EMBEDDING_DIMENSIONS` left at its 1024 default (matching `Chunk.embedding`'s column)
    boots cleanly — the happy path the mismatch test above contrasts with.
    """
    main_module = _reload_main(monkeypatch, {"EMBEDDING_DIMENSIONS": "1024"})

    assert main_module.app.title == "AdvisorDesk API"
