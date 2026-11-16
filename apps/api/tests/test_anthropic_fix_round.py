"""Test-author (RED) file for fix round "Task F" of the anthropic-haiku brief.

Pins: `Settings.llm_max_tokens` flowing into all three Anthropic adapters; `stop_reason ==
"max_tokens"` handling (agent fails closed, chat/judge log a WARNING); the pure boot-guard helper
`app.boot_checks.missing_api_key_errors(settings) -> list[str]` that `app/main.py` must use; and
two config coverage gaps from the A review. No network, DB-less.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import pytest
from pydantic import ValidationError

from app.agent.anthropic_llm import AnthropicAgentLLM
from app.agent.llm import AgentLLMFailedError
from app.boot_checks import missing_api_key_errors
from app.config import Settings
from app.eval.anthropic_judge import AnthropicJudge
from app.rag.anthropic_chat import AnthropicChatLLM
from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import SYSTEM_PROMPT

_ENV = [
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "LLM_BASE_URL",
    "LLM_MAX_TOKENS",
    "ENVIRONMENT",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


_SOURCES = (
    RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content_id=uuid.uuid4(),
        title="RSU Basics",
        slug="rsu-basics",
        text="RSUs are taxed as ordinary income at vest.",
        similarity=0.9,
    ),
)
_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "SYS"},
    {"role": "user", "content": "hi"},
]
_TOOLS = [
    {
        "name": "search_content",
        "description": "Search.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
]


# ------------------------------------------------------------------ fakes


class _CreateMessages:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class _Stream:
    def __init__(self, stop_reason: str) -> None:
        self._stop_reason = stop_reason

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self) -> Any:
        yield "partial"

    def get_final_message(self) -> Any:
        return SimpleNamespace(stop_reason=self._stop_reason)


class _StreamMessages:
    def __init__(self, stop_reason: str) -> None:
        self._stop_reason = stop_reason
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _Stream:
        self.calls.append(kwargs)
        return _Stream(self._stop_reason)


def _resp(*blocks: Any, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def _text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def _tool_use(input_: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id="tu_1", name="search_content", input=input_)


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch, messages: Any) -> None:
    """`from_settings` builds `anthropic.Anthropic(...)`; swap it for a recording fake."""
    monkeypatch.setattr(
        anthropic, "Anthropic", lambda **_kw: SimpleNamespace(messages=messages), raising=True
    )


def _settings(**kw: Any) -> Settings:
    return Settings(llm_provider="anthropic", **kw)


# ------------------------------------------------------------------ 1) llm_max_tokens


def test_llm_max_tokens_default_is_2048() -> None:
    assert Settings().llm_max_tokens == 2048


def test_llm_max_tokens_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    assert Settings().llm_max_tokens == 4096


@pytest.mark.parametrize("bad", [0, -1])
def test_llm_max_tokens_must_be_positive(bad: int) -> None:
    with pytest.raises(ValidationError):
        Settings(llm_max_tokens=bad)


def test_chat_from_settings_sends_configured_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _StreamMessages("end_turn")
    _patch_anthropic(monkeypatch, messages)
    llm = AnthropicChatLLM.from_settings(_settings(llm_max_tokens=777))
    list(llm.stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))
    assert messages.calls[0]["max_tokens"] == 777


def test_agent_from_settings_sends_configured_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _CreateMessages(_resp(_text("hello")))
    _patch_anthropic(monkeypatch, messages)
    llm = AnthropicAgentLLM.from_settings(_settings(llm_max_tokens=777))
    llm.next_step(_MESSAGES, _TOOLS)
    assert messages.calls[0]["max_tokens"] == 777


def test_agent_new_conversation_keeps_configured_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = _CreateMessages(_resp(_text("hello")))
    _patch_anthropic(monkeypatch, messages)
    llm = AnthropicAgentLLM.from_settings(_settings(llm_max_tokens=777)).new_conversation()
    llm.next_step(_MESSAGES, _TOOLS)
    assert messages.calls[0]["max_tokens"] == 777


def test_judge_from_settings_sends_configured_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = _CreateMessages(_resp(_text("YES\nok")))
    _patch_anthropic(monkeypatch, messages)
    judge = AnthropicJudge.from_settings(_settings(llm_max_tokens=777))
    judge.is_answer_relevant("q?", "a")
    assert messages.calls[0]["max_tokens"] == 777


# ------------------------------------------------------------------ 2) stop_reason max_tokens


def _agent(response: Any) -> AnthropicAgentLLM:
    client = SimpleNamespace(messages=_CreateMessages(response))
    return AnthropicAgentLLM(client=client, model="claude-haiku-5-5")  # type: ignore[arg-type]


def test_agent_truncated_tool_use_fails_closed() -> None:
    llm = _agent(_resp(_tool_use({"q": "rs"}), stop_reason="max_tokens"))
    with pytest.raises(AgentLLMFailedError) as info:
        llm.next_step(_MESSAGES, _TOOLS)
    assert "max_tokens" not in str(info.value)


def test_agent_truncated_text_fails_closed() -> None:
    llm = _agent(_resp(_text("half an ans"), stop_reason="max_tokens"))
    with pytest.raises(AgentLLMFailedError):
        llm.next_step(_MESSAGES, _TOOLS)


def test_chat_max_tokens_logs_warning_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = SimpleNamespace(messages=_StreamMessages("max_tokens"))
    llm = AnthropicChatLLM(client=client, model="claude-haiku-5-5")  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        out = list(llm.stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))
    assert out == ["partial"]
    assert any(
        r.levelno == logging.WARNING and "max_tokens" in r.getMessage() for r in caplog.records
    )


def _judge(response: Any) -> AnthropicJudge:
    client = SimpleNamespace(messages=_CreateMessages(response))
    return AnthropicJudge(client=client, model="claude-haiku-5-5")  # type: ignore[arg-type]


def test_judge_max_tokens_logs_warning_and_empty_reply_behaviour(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Truncated, unparseable batch reply -> None (same as any unparseable reply today).
    judge = _judge(_resp(_text('[{"index": 0, "rel'), stop_reason="max_tokens"))
    with caplog.at_level(logging.WARNING):
        assert judge.rank_chunk_relevance("q?", ["a"]) is None
    assert any(
        r.levelno == logging.WARNING and "max_tokens" in r.getMessage() for r in caplog.records
    )


def test_judge_max_tokens_with_no_text_yes_no_is_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    judge = _judge(_resp(stop_reason="max_tokens"))
    with caplog.at_level(logging.WARNING):
        assert judge.is_answer_relevant("q?", "a") is False
    assert "max_tokens" in caplog.text


# ------------------------------------------------------------------ 3) boot guard helper


def _prod(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("ENVIRONMENT", "production")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_boot_checks_empty_in_dev() -> None:
    assert missing_api_key_errors(Settings()) == []


def test_boot_checks_empty_when_both_keys_present(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="a", OPENAI_API_KEY="o")
    assert missing_api_key_errors(s) == []


def test_boot_checks_anthropic_active_key_missing_names_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="anthropic", OPENAI_API_KEY="o")
    errors = missing_api_key_errors(s)
    assert len(errors) == 1
    assert "ANTHROPIC_API_KEY" in errors[0]
    assert "NVIDIA_API_KEY" not in errors[0]


def test_boot_checks_anthropic_with_openai_embeddings_missing_reports_openai_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="a")
    errors = missing_api_key_errors(s)
    assert len(errors) == 1
    assert "OPENAI_API_KEY" in errors[0]
    assert "ANTHROPIC_API_KEY" not in errors[0]


def test_boot_checks_openai_missing_names_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    errors = missing_api_key_errors(_prod(monkeypatch, LLM_PROVIDER="openai"))
    assert errors
    assert all("OPENAI_API_KEY" in e for e in errors)


def test_boot_checks_nvidia_llm_and_embedding_name_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="nvidia", EMBEDDING_PROVIDER="nvidia")
    errors = missing_api_key_errors(s)
    assert errors
    assert all("NVIDIA_API_KEY" in e for e in errors)


def test_boot_checks_nvidia_llm_openai_embeddings_reports_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = _prod(monkeypatch, LLM_PROVIDER="nvidia", NVIDIA_API_KEY="n")
    errors = missing_api_key_errors(s)
    assert len(errors) == 1 and "OPENAI_API_KEY" in errors[0]


def test_main_source_uses_missing_api_key_errors() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "missing_api_key_errors" in source
    assert "boot_checks" in source


# ------------------------------------------------------------------ 4) config coverage


def test_embedding_provider_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "nvidia")
    assert Settings().embedding_provider == "nvidia"


def test_custom_llm_base_url_honored_for_embeddings_when_same_provider() -> None:
    s = Settings(
        llm_provider="openai", embedding_provider="openai", llm_base_url="https://proxy.example/v1"
    )
    assert s.embedding_base_url == "https://proxy.example/v1"
