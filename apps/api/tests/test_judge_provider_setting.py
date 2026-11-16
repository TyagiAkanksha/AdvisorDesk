"""RED (anthropic-haiku Task I, test-author): the eval judge provider is selectable independently
of the chat/agent provider (so Claude Haiku answers can be judged by the baseline gpt-5.4 judge).

Required (not yet existing) surfaces:
- `Settings.judge_provider: Literal["openai","nvidia","anthropic"] | None = None`
  (`JUDGE_PROVIDER`).
- `Settings.effective_judge_provider` -- `judge_provider` if set else `llm_provider`.
- `Settings.judge_api_key` -- SecretStr of the effective judge provider's key.
- `Settings.judge_base_url` -- `llm_base_url` when the effective judge provider == `llm_provider`,
  else that provider's well-known default URL.
- `build_judge` selects on `effective_judge_provider`; `OpenAIJudge.from_settings` refuses only
  when the effective judge provider is anthropic; `AnthropicJudge.from_settings` uses
  `judge_api_key`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.eval import anthropic_judge as anthropic_judge_module
from app.eval import groundedness as groundedness_module
from app.eval.anthropic_judge import AnthropicJudge
from app.eval.groundedness import OpenAIJudge
from app.eval.judge_factory import build_judge

_OPENAI = "sk-openai-judge-key"
_NVIDIA = "nvapi-judge-key"
_ANTHROPIC = "sk-ant-judge-key"
_OPENAI_URL = "https://api.openai.com/v1"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
_ENV_VARS = (
    "JUDGE_PROVIDER",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "JUDGE_MODEL",
    "JUDGE_TEMPERATURE",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "openai_api_key": _OPENAI,
        "nvidia_api_key": _NVIDIA,
        "anthropic_api_key": _ANTHROPIC,
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)


class _FakeOpenAI:
    instances: list[_FakeOpenAI] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _FakeOpenAI.instances.append(self)


class _FakeAnthropic:
    instances: list[_FakeAnthropic] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _FakeAnthropic.instances.append(self)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeOpenAI.instances = []
    _FakeAnthropic.instances = []
    monkeypatch.setattr(groundedness_module, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(anthropic_judge_module.anthropic, "Anthropic", _FakeAnthropic)


# --- Settings ---------------------------------------------------------------------------------


def test_judge_provider_defaults_to_none() -> None:
    assert _settings().judge_provider is None


def test_judge_provider_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    assert Settings(_env_file=None).judge_provider == "openai"  # type: ignore[call-arg]


def test_judge_provider_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(judge_provider="gemini")
    assert exc.value.errors()[0]["type"] != "extra_forbidden"  # the field must exist


@pytest.mark.parametrize("llm", ["openai", "nvidia", "anthropic"])
def test_effective_judge_provider_follows_llm_provider_when_unset(llm: str) -> None:
    assert _settings(llm_provider=llm).effective_judge_provider == llm


def test_effective_judge_provider_prefers_explicit_setting() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai")
    assert settings.effective_judge_provider == "openai"


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("openai", _OPENAI), ("nvidia", _NVIDIA), ("anthropic", _ANTHROPIC)],
)
def test_judge_api_key_matches_effective_judge_provider(provider: str, expected: str) -> None:
    key = _settings(llm_provider="openai", judge_provider=provider).judge_api_key
    assert isinstance(key, SecretStr)
    assert key.get_secret_value() == expected


def test_judge_api_key_follows_llm_provider_when_unset() -> None:
    key = _settings(llm_provider="nvidia").judge_api_key
    assert key.get_secret_value() == _NVIDIA


def test_judge_api_key_is_not_the_llm_key_when_providers_differ() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai")
    assert settings.judge_api_key.get_secret_value() == _OPENAI
    assert settings.llm_api_key.get_secret_value() == _ANTHROPIC


def test_judge_base_url_is_llm_base_url_when_same_provider() -> None:
    settings = _settings(llm_provider="nvidia", llm_base_url="https://custom.example/v1")
    assert settings.judge_base_url == "https://custom.example/v1"
    same = _settings(llm_provider="openai", judge_provider="openai", llm_base_url="https://x/v1")
    assert same.judge_base_url == "https://x/v1"


def test_judge_base_url_is_provider_default_when_different() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai")
    assert settings.judge_base_url == _OPENAI_URL
    other = _settings(
        llm_provider="openai", llm_base_url="https://custom.example/v1", judge_provider="nvidia"
    )
    assert other.judge_base_url == _NVIDIA_URL


# --- build_judge / from_settings ---------------------------------------------------------------


def test_build_judge_openai_judge_under_anthropic_chat_uses_openai_key_and_url(fakes: None) -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai", judge_model="gpt-5.4")
    judge = build_judge(settings)
    assert isinstance(judge, OpenAIJudge)
    assert _FakeAnthropic.instances == []
    assert len(_FakeOpenAI.instances) == 1
    kwargs = _FakeOpenAI.instances[0].kwargs
    assert kwargs["api_key"] == _OPENAI
    assert kwargs["base_url"] == _OPENAI_URL
    assert _ANTHROPIC not in repr(kwargs)
    assert judge._model == "gpt-5.4"  # noqa: SLF001


def test_build_judge_real_client_under_anthropic_chat_uses_openai_credentials() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai", judge_model="gpt-5.4")
    judge = build_judge(settings)
    assert isinstance(judge, OpenAIJudge)
    assert judge._client.api_key == _OPENAI  # noqa: SLF001
    assert str(judge._client.base_url).rstrip("/") == _OPENAI_URL  # noqa: SLF001


def test_build_judge_anthropic_judge_under_openai_chat_uses_anthropic_key(fakes: None) -> None:
    settings = _settings(llm_provider="openai", judge_provider="anthropic")
    judge = build_judge(settings)
    assert isinstance(judge, AnthropicJudge)
    assert _FakeOpenAI.instances == []
    assert len(_FakeAnthropic.instances) == 1
    assert _FakeAnthropic.instances[0].kwargs["api_key"] == _ANTHROPIC


def test_build_judge_anthropic_judge_never_uses_openai_key(fakes: None) -> None:
    build_judge(_settings(llm_provider="nvidia", judge_provider="anthropic"))
    assert _OPENAI not in repr(_FakeAnthropic.instances[0].kwargs)
    assert _NVIDIA not in repr(_FakeAnthropic.instances[0].kwargs)


@pytest.mark.parametrize(
    ("llm", "expected"),
    [("openai", OpenAIJudge), ("nvidia", OpenAIJudge), ("anthropic", AnthropicJudge)],
)
def test_build_judge_unset_follows_llm_provider(llm: str, expected: type) -> None:
    assert isinstance(build_judge(_settings(llm_provider=llm)), expected)


def test_build_judge_nvidia_judge_uses_nvidia_key_and_default_url(fakes: None) -> None:
    build_judge(_settings(llm_provider="anthropic", judge_provider="nvidia"))
    kwargs = _FakeOpenAI.instances[0].kwargs
    assert kwargs["api_key"] == _NVIDIA
    assert kwargs["base_url"] == _NVIDIA_URL


def test_openai_judge_from_settings_guard_keys_off_effective_judge_provider() -> None:
    with pytest.raises(ValueError, match="anthropic") as exc:
        OpenAIJudge.from_settings(_settings(llm_provider="openai", judge_provider="anthropic"))
    assert _ANTHROPIC not in str(exc.value)
    # chat provider anthropic is fine when the judge provider is not anthropic
    assert isinstance(
        OpenAIJudge.from_settings(_settings(llm_provider="anthropic", judge_provider="openai")),
        OpenAIJudge,
    )


def test_anthropic_judge_from_settings_uses_judge_api_key(fakes: None) -> None:
    AnthropicJudge.from_settings(_settings(llm_provider="openai", judge_provider="anthropic"))
    assert _FakeAnthropic.instances[0].kwargs["api_key"] == _ANTHROPIC


@pytest.mark.parametrize("temperature", [0.0, 0.3, None])
def test_openai_judge_temperature_unchanged_with_split_provider(temperature: float | None) -> None:
    settings = _settings(
        llm_provider="anthropic", judge_provider="openai", judge_temperature=temperature
    )
    judge = build_judge(settings)
    assert isinstance(judge, OpenAIJudge)
    assert judge._temperature == temperature  # noqa: SLF001
