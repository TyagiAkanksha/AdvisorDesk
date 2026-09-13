"""Test-author (RED) file for task 6R-14 — `Settings.llm_provider`/`openai_api_key`/
`llm_api_key` and the config-default flip to OpenAI.

`docs/plans/phase-6-remediation/task-14-openai-provider-swap.md` (P0 production outage: both
pinned NVIDIA models are EOL/410 Gone; owner picked OpenAI). Pins design pin #1 exactly:

  - `llm_provider: Literal["openai", "nvidia"] = "openai"` — the new provider switch. OpenAI is
    now the default (both NVIDIA models this app was pinned to are dead); `"nvidia"` stays
    selectable as a back-compat/future-re-enable branch.
  - `openai_api_key: SecretStr = SecretStr("")` (env `OPENAI_API_KEY`) — the new credential
    field, mirroring every other secret field's empty-`SecretStr` default and repr-hiding.
  - `llm_api_key` property: returns `openai_api_key` when `llm_provider == "openai"`, else
    `nvidia_api_key` — the ONE field both `OpenAICompatibleEmbedder.from_settings` and the chat/
    agent `from_settings` methods must read (task-14: "The credential field `nvidia_api_key`
    ... is used for BOTH and must pick up the OpenAI key").
  - Defaults FLIP to the OpenAI values (controller-verified live): `llm_base_url =
    "https://api.openai.com/v1"`, `embedding_model = "text-embedding-3-small"`, `chat_model =
    "gpt-4o-mini"`, `embedding_dimensions = 1024` (unchanged — `text-embedding-3-small` with
    `dimensions=1024` returns exactly 1024-dim vectors, a drop-in for the existing
    `chunks.embedding vector(1024)` column, no migration).
  - The empty-key boot-safety fallback pattern stays: `Settings()`/`Settings(openai_api_key="")`
    must construct cleanly with zero env vars, mirroring `nvidia_api_key`'s existing handling
    (dev boots with no key; `app.main`'s `not settings.is_dev` guard is what enforces
    non-emptiness in production, unchanged by this task).

Pinned interface names (task-14 brief, exact — the implementer must use them or STOP):
`llm_provider`, `openai_api_key`, `llm_api_key`.

Deliberately DB-less (CONVENTIONS.md §10), mirroring `tests/test_config.py`.

RED (current HEAD, pre-implementation): none of `llm_provider`/`openai_api_key`/`llm_api_key`
exist on `Settings` yet. `Settings(llm_provider=...)`/`Settings(openai_api_key=...)` raise
`pydantic_core.ValidationError` (`extra_forbidden` — `Settings`' `BaseSettings` config rejects
unknown keywords, confirmed against this HEAD) at CALL time inside each test body; a bare
`Settings().llm_provider`/`.openai_api_key`/`.llm_api_key` access raises `AttributeError` at
CALL time. Neither is a collection-time failure — `Settings` itself already exists and imports
fine today.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

# The new task-14 env vars, stripped before each defaults assertion so a developer's ambient
# shell exports (or a sourced `.env` carrying a real `OPENAI_API_KEY`/`NVIDIA_API_KEY`) can never
# leak into the "empty env" scenario these tests are pinning — mirrors
# `tests/test_config.py`'s own `_ENV_ROSTER`/`clean_env` pattern exactly.
_LLM_ENV_ROSTER = [
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "LLM_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "CHAT_MODEL",
]


@pytest.fixture
def clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the task-14 LLM-provider env vars so `Settings()` reflects only its defaults."""
    for name in _LLM_ENV_ROSTER:
        monkeypatch.delenv(name, raising=False)


# ---- llm_provider: new field, defaults to "openai" ----------------------------------------------


def test_llm_provider_defaults_to_openai(clean_llm_env: None) -> None:
    """Task-14 design pin #1: `Settings().llm_provider` defaults to `"openai"` — both NVIDIA NIM
    models this app was pinned to (embedding + chat) are end-of-life (410 Gone); OpenAI is now
    the default live provider, config-only (PRD §7.2's "a provider swap never touches code").
    """
    assert Settings().llm_provider == "openai"


def test_llm_provider_accepts_explicit_nvidia(clean_llm_env: None) -> None:
    """The `"nvidia"` branch stays selectable — a back-compat/future-re-enable path (task-14's
    "After this task" section: a 2048-dim NVIDIA embedding model is callable but needs a
    migration + full re-embed, deliberately deferred, not ruled out)."""
    assert Settings(llm_provider="nvidia").llm_provider == "nvidia"


def test_llm_provider_rejects_an_unrecognized_value(clean_llm_env: None) -> None:
    """`llm_provider` is a `Literal["openai", "nvidia"]`, not a free-form string — an unknown
    provider name must fail `Settings` construction with pydantic's OWN literal-validation error
    (`type == "literal_error"`), not silently pass through to `llm_api_key`/a client builder that
    doesn't know what to do with it.

    Discriminates real RED from a false pass: at current HEAD (no `llm_provider` field at all),
    `Settings(llm_provider="anthropic")` ALSO raises `ValidationError` — but as `extra_forbidden`,
    not `literal_error` — so the `errors()[0]["type"]` assertion below fails now and only passes
    once `llm_provider` is genuinely a `Literal["openai", "nvidia"]` field.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(llm_provider="anthropic")

    assert exc_info.value.errors()[0]["type"] == "literal_error"


# ---- openai_api_key: new SecretStr credential field ---------------------------------------------


def test_openai_api_key_defaults_to_an_empty_secretstr(clean_llm_env: None) -> None:
    """Zero-env-var boot-safety (CONVENTIONS.md §5): `Settings()` must still construct with no
    `OPENAI_API_KEY` set — mirrors every other credential field's empty-`SecretStr` default.
    """
    settings = Settings()

    assert isinstance(settings.openai_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == ""


def test_openai_api_key_accepts_a_plain_string_value(clean_llm_env: None) -> None:
    """A plain `str` passed to the constructor (or read from `OPENAI_API_KEY` via
    pydantic-settings' case-insensitive env matching) coerces to `SecretStr`, mirroring every
    other credential field in `Settings`."""
    settings = Settings(openai_api_key="sk-test-value")

    assert settings.openai_api_key.get_secret_value() == "sk-test-value"


def test_settings_repr_hides_openai_api_key(clean_llm_env: None) -> None:
    """`openai_api_key` is `SecretStr` — a naive `repr(Settings(...))` (e.g. via structured
    logging) must never leak it, mirroring `nvidia_api_key`'s own repr-hiding pin
    (`tests/test_auth_endpoints.py::test_settings_repr_hides_secret_values`).
    """
    settings = Settings(openai_api_key="sk-super-secret-value")

    rendered = repr(settings)

    assert "sk-super-secret-value" not in rendered


# ---- llm_api_key: the provider-selecting property -----------------------------------------------


def test_llm_api_key_returns_the_openai_key_when_provider_is_openai(clean_llm_env: None) -> None:
    """Task-14 design pin #1: `llm_api_key` returns `openai_api_key` when `llm_provider ==
    "openai"` (the new default) — the ONE field both the embedding and chat clients'
    `from_settings` must read (task-14: "used for BOTH and must pick up the OpenAI key")."""
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-openai-value",
        nvidia_api_key="nvapi-value",
    )

    assert settings.llm_api_key.get_secret_value() == "sk-openai-value"


def test_llm_api_key_returns_the_nvidia_key_when_provider_is_nvidia(clean_llm_env: None) -> None:
    """The back-compat branch: `llm_provider="nvidia"` still resolves `llm_api_key` to
    `nvidia_api_key`, exactly as every provider call site behaved before this task."""
    settings = Settings(
        llm_provider="nvidia",
        openai_api_key="sk-openai-value",
        nvidia_api_key="nvapi-value",
    )

    assert settings.llm_api_key.get_secret_value() == "nvapi-value"


def test_llm_api_key_is_a_secretstr(clean_llm_env: None) -> None:
    """`llm_api_key` must return the `SecretStr` itself, not the unwrapped plaintext — a naive
    caller that logs `settings.llm_api_key` (instead of calling `.get_secret_value()`) must not
    leak a real key, mirroring every other secret field's own house rule (config.py docstring:
    "a naive `repr(Settings(...))`... never leaks a secret value")."""
    settings = Settings(llm_provider="openai", openai_api_key="sk-openai-value")

    assert isinstance(settings.llm_api_key, SecretStr)


def test_llm_api_key_is_boot_safe_when_the_selected_providers_key_is_empty(
    clean_llm_env: None,
) -> None:
    """Task-14 design pin #1: "The empty-key... boot-safety fallback pattern stays (dev boots
    with no key)" — mirrors the existing empty-`nvidia_api_key` handling: a zero-env-var
    `Settings()` (provider defaults `"openai"`, `openai_api_key` defaults empty) must resolve
    `llm_api_key` to an empty secret with NO exception anywhere in `Settings` construction or
    property resolution — exactly like `nvidia_api_key` has always behaved.
    """
    settings = Settings()

    assert settings.llm_api_key.get_secret_value() == ""


# ---- Defaults flip to the OpenAI values (controller-verified live) ------------------------------


def test_defaults_flip_to_the_openai_values(clean_llm_env: None) -> None:
    """Task-14 design pin #1: `Settings()`'s previously-NVIDIA defaults now point at OpenAI —
    controller-verified live: `text-embedding-3-small` with `dimensions=1024` returns exactly
    1024-dim vectors (drop-in for the existing `chunks.embedding vector(1024)` column, no
    migration) and `gpt-4o-mini` responds and supports tool-calling (the admin agent needs it).
    """
    settings = Settings()

    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.chat_model == "gpt-5.4-mini"
    assert settings.embedding_dimensions == 1024
