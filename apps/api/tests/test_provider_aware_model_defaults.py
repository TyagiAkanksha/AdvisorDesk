"""RED (anthropic-haiku Task J, test-author): `chat_model`/`judge_model` defaults follow the
provider, and an explicit model whose family contradicts its provider fails fast.

Production deliberately does not pin CHAT_MODEL/JUDGE_MODEL (tests/test_prod_config_pins.py), so
the code default must be right for whichever provider is active:

- chat_model unset: `llm_provider == "anthropic"` -> "claude-haiku-5-5", else "gpt-5.4-mini".
- judge_model unset: `effective_judge_provider == "anthropic"` -> "claude-haiku-5-5", else
  "gpt-5.4" (so the split `llm_provider=anthropic` + `judge_provider=openai` keeps the baseline
  gpt-5.4 judge).
- An explicit value (kwarg or env) is never silently rewritten; a family mismatch is rejected by
  the guard below instead.
- Mismatch guard, at Settings construction (ValueError/ValidationError naming the setting, never
  echoing a key): explicit "claude-*" model under openai/nvidia, explicit "gpt-*" model under
  anthropic. Other names (e.g. "meta/llama-3.1-8b-instruct") are not judged by prefix, except
  that "gpt-" is still rejected under anthropic.

DB-less; env isolation via monkeypatch (Settings is built with `_env_file=None`).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings

_HAIKU = "claude-haiku-5-5"
_CHAT_DEFAULT = "gpt-5.4-mini"
_JUDGE_DEFAULT = "gpt-5.4"
_OPENAI_KEY = "sk-openai-secret-do-not-leak"
_ANTHROPIC_KEY = "sk-ant-secret-do-not-leak"
_ENV_VARS = (
    "LLM_PROVIDER",
    "JUDGE_PROVIDER",
    "CHAT_MODEL",
    "JUDGE_MODEL",
    "LLM_BASE_URL",
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
        "openai_api_key": _OPENAI_KEY,
        "anthropic_api_key": _ANTHROPIC_KEY,
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)


# --- chat_model default follows llm_provider ----------------------------------------------------


def test_chat_model_defaults_to_haiku_under_anthropic() -> None:
    assert _settings(llm_provider="anthropic").chat_model == _HAIKU


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_chat_model_default_unchanged_for_openai_and_nvidia(provider: str) -> None:
    assert _settings(llm_provider=provider).chat_model == _CHAT_DEFAULT


def test_chat_model_default_unchanged_when_provider_unset() -> None:
    assert _settings().chat_model == _CHAT_DEFAULT


def test_chat_model_default_under_anthropic_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert Settings(_env_file=None).chat_model == _HAIKU  # type: ignore[call-arg]


def test_explicit_chat_model_kwarg_wins_under_anthropic() -> None:
    settings = _settings(llm_provider="anthropic", chat_model="claude-opus-9")
    assert settings.chat_model == "claude-opus-9"


def test_explicit_chat_model_env_wins_under_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_MODEL", "claude-sonnet-5-5")
    assert Settings(_env_file=None).chat_model == "claude-sonnet-5-5"  # type: ignore[call-arg]


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_explicit_chat_model_wins_under_openai_and_nvidia(provider: str) -> None:
    assert _settings(llm_provider=provider, chat_model="gpt-4o-mini").chat_model == "gpt-4o-mini"


def test_explicit_default_valued_gpt_chat_model_is_not_silently_overridden() -> None:
    # No silent override: an explicit "gpt-5.4-mini" under anthropic is the operator's value, so
    # it is rejected loudly (mismatch guard) rather than rewritten to Haiku.
    with pytest.raises(ValueError, match="chat_model"):
        _settings(llm_provider="anthropic", chat_model=_CHAT_DEFAULT)


def test_explicit_default_valued_gpt_chat_model_from_env_is_not_silently_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_MODEL", _CHAT_DEFAULT)
    with pytest.raises(ValueError, match="chat_model"):
        Settings(_env_file=None)  # type: ignore[call-arg]


# --- judge_model default follows effective_judge_provider ---------------------------------------


def test_judge_model_defaults_to_haiku_under_anthropic() -> None:
    assert _settings(llm_provider="anthropic").judge_model == _HAIKU


def test_judge_model_defaults_to_haiku_when_only_judge_provider_is_anthropic() -> None:
    settings = _settings(llm_provider="openai", judge_provider="anthropic")
    assert settings.judge_model == _HAIKU
    assert settings.chat_model == _CHAT_DEFAULT


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_judge_model_default_unchanged_for_openai_and_nvidia(provider: str) -> None:
    assert _settings(llm_provider=provider).judge_model == _JUDGE_DEFAULT


def test_judge_model_default_unchanged_when_provider_unset() -> None:
    assert _settings().judge_model == _JUDGE_DEFAULT


def test_split_case_anthropic_chat_openai_judge_keeps_baseline_judge_model() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai")
    assert settings.chat_model == _HAIKU
    assert settings.judge_model == _JUDGE_DEFAULT


def test_split_case_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.chat_model == _HAIKU
    assert settings.judge_model == _JUDGE_DEFAULT


def test_explicit_judge_model_kwarg_wins() -> None:
    assert _settings(llm_provider="anthropic", judge_model="claude-opus-9").judge_model == (
        "claude-opus-9"
    )
    assert _settings(llm_provider="openai", judge_model="gpt-4o").judge_model == "gpt-4o"


def test_explicit_judge_model_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("JUDGE_MODEL", "claude-sonnet-5-5")
    assert Settings(_env_file=None).judge_model == "claude-sonnet-5-5"  # type: ignore[call-arg]


def test_explicit_default_valued_gpt_judge_model_is_not_silently_overridden() -> None:
    with pytest.raises(ValueError, match="judge_model"):
        _settings(llm_provider="anthropic", judge_model=_JUDGE_DEFAULT)


# --- mismatch guard: chat_model vs llm_provider -------------------------------------------------


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_claude_chat_model_rejected_under_openai_and_nvidia(provider: str) -> None:
    with pytest.raises(ValueError, match="chat_model") as exc:
        _settings(llm_provider=provider, chat_model=_HAIKU)
    assert _OPENAI_KEY not in str(exc.value)
    assert _ANTHROPIC_KEY not in str(exc.value)


def test_claude_chat_model_rejected_when_llm_provider_defaults_to_openai() -> None:
    with pytest.raises(ValueError, match="chat_model"):
        _settings(chat_model=_HAIKU)


def test_claude_chat_model_from_env_rejected_under_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", _HAIKU)
    with pytest.raises(ValueError, match="chat_model"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize("model", ["gpt-5.4-mini", "gpt-4o"])
def test_gpt_chat_model_rejected_under_anthropic(model: str) -> None:
    with pytest.raises(ValueError, match="chat_model") as exc:
        _settings(llm_provider="anthropic", chat_model=model)
    assert _ANTHROPIC_KEY not in str(exc.value)
    assert _OPENAI_KEY not in str(exc.value)


def test_non_prefixed_chat_model_allowed_under_nvidia_and_openai() -> None:
    model = "meta/llama-3.1-8b-instruct"
    assert _settings(llm_provider="nvidia", chat_model=model).chat_model == model
    assert _settings(llm_provider="openai", chat_model=model).chat_model == model


def test_non_gpt_chat_model_allowed_under_anthropic() -> None:
    model = "meta/llama-3.1-8b-instruct"
    assert _settings(llm_provider="anthropic", chat_model=model).chat_model == model


# --- mismatch guard: judge_model vs effective_judge_provider ------------------------------------


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_claude_judge_model_rejected_under_openai_and_nvidia_judge(provider: str) -> None:
    with pytest.raises(ValueError, match="judge_model") as exc:
        _settings(llm_provider=provider, judge_model=_HAIKU)
    assert _OPENAI_KEY not in str(exc.value)
    assert _ANTHROPIC_KEY not in str(exc.value)


def test_claude_judge_model_rejected_when_judge_provider_is_openai_under_anthropic_chat() -> None:
    with pytest.raises(ValueError, match="judge_model"):
        _settings(llm_provider="anthropic", judge_provider="openai", judge_model=_HAIKU)


def test_gpt_judge_model_rejected_under_anthropic_judge() -> None:
    with pytest.raises(ValueError, match="judge_model") as exc:
        _settings(llm_provider="anthropic", judge_model="gpt-5.4")
    assert _ANTHROPIC_KEY not in str(exc.value)
    assert _OPENAI_KEY not in str(exc.value)


def test_gpt_judge_model_rejected_when_judge_provider_is_anthropic_under_openai_chat() -> None:
    with pytest.raises(ValueError, match="judge_model"):
        _settings(llm_provider="openai", judge_provider="anthropic", judge_model="gpt-5.4")


def test_split_case_explicit_gpt_judge_model_allowed() -> None:
    settings = _settings(llm_provider="anthropic", judge_provider="openai", judge_model="gpt-5.4")
    assert settings.judge_model == "gpt-5.4"
    assert settings.chat_model == _HAIKU


def test_non_prefixed_judge_model_allowed_under_nvidia_and_anthropic_judge() -> None:
    model = "meta/llama-3.1-8b-instruct"
    assert _settings(llm_provider="nvidia", judge_model=model).judge_model == model
    assert _settings(llm_provider="anthropic", judge_model=model).judge_model == model
