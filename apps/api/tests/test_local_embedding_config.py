"""Test-author (RED) file for Task A of the local-embeddings brief — config (A1), boot checks
(A5) and the dependency pin (A6). DB-less. `Settings` has no env_file, so isolation = stripping
env vars via monkeypatch.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.boot_checks import missing_api_key_errors
from app.config import Settings

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

_ENV = [
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "LLM_BASE_URL",
    "SIMILARITY_THRESHOLD",
    "ENVIRONMENT",
    "LOCAL_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_QUERY_PREFIX",
    "LOCAL_EMBEDDING_CACHE_DIR",
    "LOCAL_EMBEDDING_OFFLINE",
    "LOCAL_EMBEDDING_THREADS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


# ---- A1: provider + new fields ----


def test_embedding_provider_accepts_local_and_default_is_still_openai() -> None:
    assert Settings(embedding_provider="local").embedding_provider == "local"
    assert Settings().embedding_provider == "openai"


def test_embedding_provider_still_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_provider="bogus")  # type: ignore[arg-type]


def test_local_embedding_defaults() -> None:
    s = Settings()
    assert s.local_embedding_model == "BAAI/bge-small-en-v1.5"
    assert (
        s.local_embedding_query_prefix
        == "Represent this sentence for searching relevant passages: "
    )
    assert s.local_embedding_cache_dir is None
    assert s.local_embedding_offline is False
    assert s.local_embedding_threads == 2


def test_local_embedding_fields_read_from_upper_cased_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "org/other-model")
    monkeypatch.setenv("LOCAL_EMBEDDING_QUERY_PREFIX", "query: ")
    monkeypatch.setenv("LOCAL_EMBEDDING_CACHE_DIR", "/app/.fastembed-cache")
    monkeypatch.setenv("LOCAL_EMBEDDING_OFFLINE", "true")
    monkeypatch.setenv("LOCAL_EMBEDDING_THREADS", "4")
    s = Settings()
    assert s.local_embedding_model == "org/other-model"
    assert s.local_embedding_query_prefix == "query: "
    assert s.local_embedding_cache_dir == "/app/.fastembed-cache"
    assert s.local_embedding_offline is True
    assert s.local_embedding_threads == 4


@pytest.mark.parametrize("bad", [0, -1])
def test_local_embedding_threads_must_be_positive(bad: int) -> None:
    with pytest.raises(ValidationError):
        Settings(local_embedding_threads=bad)


def test_embedding_api_key_is_empty_for_local_even_with_other_keys() -> None:
    s = Settings(embedding_provider="local", openai_api_key="sk-o", nvidia_api_key="nv")
    assert s.embedding_api_key.get_secret_value() == ""


def test_embedding_base_url_is_empty_for_local() -> None:
    assert Settings(embedding_provider="local").embedding_base_url == ""
    assert Settings(embedding_provider="local", llm_provider="anthropic").embedding_base_url == ""


def test_openai_embedding_key_and_url_unchanged() -> None:
    s = Settings(openai_api_key="sk-o")
    assert s.embedding_api_key.get_secret_value() == "sk-o"
    assert s.embedding_base_url == "https://api.openai.com/v1"


# ---- A1: provider-aware similarity_threshold ----


def test_similarity_threshold_default_is_0_65_for_local() -> None:
    assert Settings(embedding_provider="local").similarity_threshold == 0.65


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_similarity_threshold_default_stays_0_5_for_other_providers(provider: str) -> None:
    kwargs = {"llm_provider": "nvidia"} if provider == "nvidia" else {}
    s = Settings(embedding_provider=provider, **kwargs)  # type: ignore[arg-type]
    assert s.similarity_threshold == 0.5


def test_explicit_similarity_threshold_wins_for_local() -> None:
    assert (
        Settings(embedding_provider="local", similarity_threshold=0.5).similarity_threshold == 0.5
    )
    assert (
        Settings(embedding_provider="local", similarity_threshold=0.3).similarity_threshold == 0.3
    )


def test_explicit_similarity_threshold_from_env_wins_for_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.42")
    assert Settings().similarity_threshold == 0.42


def test_local_threshold_default_does_not_mark_field_as_explicitly_set() -> None:
    s = Settings(embedding_provider="local")
    assert s.similarity_threshold == 0.65
    assert "similarity_threshold" not in s.model_fields_set


def test_explicit_similarity_threshold_stays_in_fields_set() -> None:
    s = Settings(embedding_provider="local", similarity_threshold=0.5)
    assert "similarity_threshold" in s.model_fields_set


# ---- A5: boot checks ----


def _prod(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("ENVIRONMENT", "production")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_boot_checks_no_embedding_key_required_for_local(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _prod(
        monkeypatch,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="sk-ant",
        EMBEDDING_PROVIDER="local",
    )
    assert s.openai_api_key.get_secret_value() == ""
    assert missing_api_key_errors(s) == []


def test_boot_checks_local_embedding_still_requires_llm_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="anthropic", EMBEDDING_PROVIDER="local")
    errors = missing_api_key_errors(s)
    assert len(errors) == 1
    assert "ANTHROPIC_API_KEY" in errors[0]
    assert "OPENAI_API_KEY" not in errors[0]


def test_boot_checks_openai_embedding_key_still_required_when_not_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant")
    errors = missing_api_key_errors(s)
    assert len(errors) == 1
    assert "OPENAI_API_KEY" in errors[0]


# ---- A6: dependency ----


def test_fastembed_is_a_runtime_dependency() -> None:
    deps = tomllib.loads(_PYPROJECT.read_text())["project"]["dependencies"]
    assert any(d.lower().replace("_", "-").startswith("fastembed") for d in deps), deps
