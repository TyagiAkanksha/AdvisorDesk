"""Test-author (RED) file for Task A of the anthropic-haiku brief — Anthropic provider config.

Pins: `llm_provider` accepts "anthropic"; `anthropic_api_key` (env ANTHROPIC_API_KEY, alias
CLAUDE_API_KEY); `llm_api_key` resolves to it under anthropic; new `embedding_provider`
(default "openai") with `embedding_api_key`, so embeddings stay on OpenAI when
llm_provider=anthropic; no base-url-mismatch warning for anthropic.

DB-less. `Settings` has no env_file, so isolation = stripping env vars via monkeypatch.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.rag.embeddings import OpenAICompatibleEmbedder

_ENV = [
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "LLM_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "CHAT_MODEL",
    "JUDGE_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def test_llm_provider_accepts_anthropic() -> None:
    assert Settings(llm_provider="anthropic").llm_provider == "anthropic"


def test_llm_provider_still_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_provider="bogus")  # type: ignore[arg-type]


def test_anthropic_api_key_defaults_empty_and_hidden() -> None:
    settings = Settings()
    assert settings.anthropic_api_key.get_secret_value() == ""
    assert "sk-ant-secret" not in repr(Settings(anthropic_api_key="sk-ant-secret"))


def test_anthropic_api_key_from_anthropic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-anthropic")
    assert Settings().anthropic_api_key.get_secret_value() == "sk-ant-from-anthropic"


def test_anthropic_api_key_from_claude_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-from-claude")
    assert Settings().anthropic_api_key.get_secret_value() == "sk-ant-from-claude"


def test_llm_api_key_returns_anthropic_key_under_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-1")
    settings = Settings(llm_provider="anthropic")
    assert settings.llm_api_key.get_secret_value() == "sk-ant-1"


def test_llm_api_key_unchanged_for_openai_and_nvidia() -> None:
    assert (
        Settings(
            llm_provider="openai", openai_api_key="o", nvidia_api_key="n", anthropic_api_key="a"
        ).llm_api_key.get_secret_value()
        == "o"
    )
    assert (
        Settings(
            llm_provider="nvidia", openai_api_key="o", nvidia_api_key="n", anthropic_api_key="a"
        ).llm_api_key.get_secret_value()
        == "n"
    )


def test_embedding_provider_defaults_to_openai() -> None:
    assert Settings().embedding_provider == "openai"


def test_embedding_provider_accepts_nvidia_and_rejects_anthropic() -> None:
    assert Settings(embedding_provider="nvidia").embedding_provider == "nvidia"
    with pytest.raises(ValidationError):
        Settings(embedding_provider="anthropic")  # type: ignore[arg-type]


def test_embedding_api_key_is_openai_key_even_under_anthropic_llm() -> None:
    settings = Settings(
        llm_provider="anthropic",
        openai_api_key="sk-openai-emb",
        anthropic_api_key="sk-ant-x",
        nvidia_api_key="nv",
    )
    assert settings.embedding_api_key.get_secret_value() == "sk-openai-emb"


def test_embedding_api_key_follows_embedding_provider_nvidia() -> None:
    settings = Settings(embedding_provider="nvidia", openai_api_key="o", nvidia_api_key="nv")
    assert settings.embedding_api_key.get_secret_value() == "nv"


def test_embedder_from_settings_uses_openai_key_and_base_url_under_anthropic() -> None:
    settings = Settings(
        llm_provider="anthropic",
        openai_api_key="sk-openai-emb",
        anthropic_api_key="sk-ant-x",
    )
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    assert embedder._client.api_key == "sk-openai-emb"
    assert str(embedder._client.base_url).startswith("https://api.openai.com/v1")
    assert embedder._provider == "openai"


def test_embedder_from_settings_keys_off_embedding_provider_not_llm_provider() -> None:
    settings = Settings(
        llm_provider="openai",
        embedding_provider="nvidia",
        openai_api_key="o",
        nvidia_api_key="nv-emb",
        llm_base_url="https://api.openai.com/v1",
    )
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    assert embedder._client.api_key == "nv-emb"
    assert "integrate.api.nvidia.com" in str(embedder._client.base_url)
    assert embedder._provider == "nvidia"


def test_no_base_url_mismatch_warning_for_anthropic(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        Settings(llm_provider="anthropic")
    assert not [r for r in caplog.records if "llm_base_url" in r.getMessage()]


def test_existing_defaults_unchanged() -> None:
    settings = Settings()
    assert settings.llm_provider == "openai"
    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1024
    assert settings.llm_api_key.get_secret_value() == ""
