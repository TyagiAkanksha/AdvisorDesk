"""Test-author (RED) file for "Task G": the effort sent to Claude is configurable.

Pins `Settings.llm_effort` (env LLM_EFFORT, default "low") flowing through `from_settings` into
`output_config={"effort": ...}` on all three Anthropic adapters. No network, DB-less.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import anthropic
import pytest
from pydantic import ValidationError

from app.agent.anthropic_llm import AnthropicAgentLLM
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
    "LLM_EFFORT",
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
_SAMPLING = ("temperature", "top_p", "top_k")


class _CreateMessages:
    def __init__(self, response: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class _Stream:
    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self) -> Any:
        yield "partial"

    def get_final_message(self) -> Any:
        return SimpleNamespace(stop_reason="end_turn")


class _StreamMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _Stream:
        self.calls.append(kwargs)
        return _Stream()


def _text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def _resp(t: str) -> SimpleNamespace:
    return SimpleNamespace(content=[_text(t)], stop_reason="end_turn")


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch, messages: Any) -> None:
    monkeypatch.setattr(
        anthropic, "Anthropic", lambda **_kw: SimpleNamespace(messages=messages), raising=True
    )


def _settings(**kw: Any) -> Settings:
    return Settings(llm_provider="anthropic", **kw)


# ------------------------------------------------------------------ Settings


def test_llm_effort_default_is_low() -> None:
    assert Settings().llm_effort == "low"


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max"])
def test_llm_effort_env_parses(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    monkeypatch.setenv("LLM_EFFORT", level)
    assert Settings().llm_effort == level


@pytest.mark.parametrize("bad", ["extreme", "", "LOW-ish"])
def test_llm_effort_invalid_env_rejected(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("LLM_EFFORT", bad)
    with pytest.raises(ValidationError):
        Settings()


# ------------------------------------------------------------------ adapters


def _chat_call(monkeypatch: pytest.MonkeyPatch, **kw: Any) -> dict[str, Any]:
    messages = _StreamMessages()
    _patch_anthropic(monkeypatch, messages)
    llm = AnthropicChatLLM.from_settings(_settings(**kw))
    list(llm.stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))
    return messages.calls[0]


def _agent_call(
    monkeypatch: pytest.MonkeyPatch, *, fresh: bool = False, **kw: Any
) -> dict[str, Any]:
    messages = _CreateMessages(_resp("hello"))
    _patch_anthropic(monkeypatch, messages)
    llm = AnthropicAgentLLM.from_settings(_settings(**kw))
    if fresh:
        llm = llm.new_conversation()
    llm.next_step(_MESSAGES, _TOOLS)
    return messages.calls[0]


def _judge_call(monkeypatch: pytest.MonkeyPatch, **kw: Any) -> dict[str, Any]:
    messages = _CreateMessages(_resp("YES\nok"))
    _patch_anthropic(monkeypatch, messages)
    AnthropicJudge.from_settings(_settings(**kw)).is_answer_relevant("q?", "a")
    return messages.calls[0]


def test_chat_sends_configured_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _chat_call(monkeypatch, llm_effort="medium")["output_config"] == {"effort": "medium"}


def test_agent_sends_configured_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _agent_call(monkeypatch, llm_effort="medium")["output_config"] == {"effort": "medium"}


def test_judge_sends_configured_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _judge_call(monkeypatch, llm_effort="medium")["output_config"] == {"effort": "medium"}


def test_agent_new_conversation_carries_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    call = _agent_call(monkeypatch, fresh=True, llm_effort="high")
    assert call["output_config"] == {"effort": "high"}


@pytest.mark.parametrize("call", [_chat_call, _agent_call, _judge_call])
def test_default_effort_sent_is_low(monkeypatch: pytest.MonkeyPatch, call: Any) -> None:
    assert call(monkeypatch)["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("call", [_chat_call, _agent_call, _judge_call])
def test_no_sampling_params_with_effort_set(monkeypatch: pytest.MonkeyPatch, call: Any) -> None:
    kwargs = call(monkeypatch, llm_effort="max")
    assert kwargs["output_config"] == {"effort": "max"}
    for name in _SAMPLING:
        assert name not in kwargs


def test_direct_ctor_effort_keyword_defaults_low_and_overrides() -> None:
    client: Any = SimpleNamespace(messages=_CreateMessages(_resp("YES\nok")))
    judge = AnthropicJudge(client=client, model="claude-haiku-5-5", effort="xhigh")
    judge.is_answer_relevant("q?", "a")
    assert client.messages.calls[0]["output_config"] == {"effort": "xhigh"}
