"""P7 remediation (fresh-review F2) — `Settings` gains a lightweight `model_validator` tying
`llm_provider` to `llm_base_url`, so a partial provider flip warns instead of booting clean and
failing opaquely at the first real request.

Before this fix, `llm_provider`/`llm_base_url`/`embedding_model`/`chat_model`/
`embedding_dimensions` were five independently-settable fields with nothing tying them together:
`Settings(llm_provider="nvidia")` alone (leaving `llm_base_url` at its OpenAI default) booted
cleanly and only failed once a real request went to the wrong endpoint with the wrong
credential/wire-shape — task 6R-14's own outage class, one layer removed.

Deliberately DB-less (CONVENTIONS.md §10), mirroring `tests/test_config.py`/`tests/test_llm_
provider_config.py`. The fix is a WARNING, never a validation error (`Settings` construction must
still succeed in every case below) — a hard block would reject a legitimate custom/self-hosted
OpenAI-compatible `llm_base_url`, which that field's own docstring explicitly allows.
"""

from __future__ import annotations

import logging

import pytest

from app.config import Settings


def test_provider_mismatch_nvidia_with_openai_default_base_url_warns_but_still_constructs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The core F2 pin: `llm_provider="nvidia"` with `llm_base_url` left at the OpenAI default
    (the exact task 6R-14 outage shape — an operator flips the provider and forgets the
    companion fields) must log a WARNING naming both the provider and the mismatched URL, while
    `Settings` construction still succeeds (a hard block would be a regression — see module
    docstring)."""
    with caplog.at_level(logging.WARNING):
        settings = Settings(llm_provider="nvidia", llm_base_url="https://api.openai.com/v1")

    assert settings.llm_provider == "nvidia"
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "llm_base_url" in r.getMessage()
    ]
    assert matches, [r.getMessage() for r in caplog.records]


def test_provider_mismatch_openai_with_nvidia_default_base_url_warns_but_still_constructs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Symmetry check: the reverse mismatch (`llm_provider="openai"` but `llm_base_url` still
    the NVIDIA NIM endpoint) must also warn — the check is not one-directional."""
    with caplog.at_level(logging.WARNING):
        settings = Settings(
            llm_provider="openai", llm_base_url="https://integrate.api.nvidia.com/v1"
        )

    assert settings.llm_provider == "openai"
    matches = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "llm_base_url" in r.getMessage()
    ]
    assert matches, [r.getMessage() for r in caplog.records]


def test_default_settings_never_warn(caplog: pytest.LogCaptureFixture) -> None:
    """A zero-env-var `Settings()` (provider `"openai"`, base_url its own matching default) is
    perfectly consistent — it must never warn."""
    with caplog.at_level(logging.WARNING):
        Settings()

    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_consistent_nvidia_provider_config_never_warns(caplog: pytest.LogCaptureFixture) -> None:
    """An operator who correctly flips ALL the companion fields (`llm_provider="nvidia"` WITH
    the matching NVIDIA `llm_base_url`) must never warn — this is a legitimate, fully-consistent
    back-compat configuration, not a mistake."""
    with caplog.at_level(logging.WARNING):
        Settings(llm_provider="nvidia", llm_base_url="https://integrate.api.nvidia.com/v1")

    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_custom_self_hosted_base_url_never_warns(caplog: pytest.LogCaptureFixture) -> None:
    """The 'don't block valid custom configs' requirement: an `llm_base_url` pointed at a
    self-hosted/third-party OpenAI-compatible proxy — neither provider's own well-known default —
    must never warn, no matter which `llm_provider` is selected."""
    with caplog.at_level(logging.WARNING):
        settings = Settings(
            llm_provider="openai", llm_base_url="https://my-custom-proxy.internal.example/v1"
        )

    assert settings.llm_base_url == "https://my-custom-proxy.internal.example/v1"
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
