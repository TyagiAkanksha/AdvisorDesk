"""Test-author (RED) file for the Anthropic chat provider (anthropic-haiku brief, Task B).

Implementer must create `app/rag/anthropic_chat.py::AnthropicChatLLM` (`__init__(*, client,
model)`, `from_settings(settings)`, `stream_answer(system, question, sources)`) and
`app.rag.chat_provider.build_chat_llm(settings) -> ChatLLM` (the provider-selection seam;
`app.main` then sets `chat_llm = build_chat_llm(settings)`, importing app.main in a test needs a
live DATABASE_URL so the seam lives in its own module). No network: a stub client stands in for
`anthropic.Anthropic` (CONVENTIONS.md §10).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any

import anthropic
import httpx
import pytest

from app.config import Settings
from app.rag.anthropic_chat import AnthropicChatLLM
from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import (
    SYSTEM_PROMPT,
    ChatCompletionFailedError,
    OpenAICompatibleChatLLM,
    _build_user_message,
)

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
_SECRET_DETAIL = "sk-ant-LEAKY-provider-detail"


class _FinalMessage:
    def __init__(self, stop_reason: str) -> None:
        self.stop_reason = stop_reason


class _FakeStream:
    def __init__(self, deltas: list[str], stop_reason: str, error: Exception | None) -> None:
        self._deltas = deltas
        self._stop_reason = stop_reason
        self._error = error

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    @property
    def text_stream(self) -> Iterator[str]:
        yield from self._deltas
        if self._error is not None:
            raise self._error

    def get_final_message(self) -> _FinalMessage:
        return _FinalMessage(self._stop_reason)


class _FakeMessages:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        return self._stream


class _FakeClient:
    def __init__(
        self,
        deltas: list[str] | None = None,
        *,
        stop_reason: str = "end_turn",
        error: Exception | None = None,
    ) -> None:
        self.messages = _FakeMessages(_FakeStream(deltas or [], stop_reason, error))


def _llm(client: _FakeClient, model: str = "claude-haiku-5-5") -> AnthropicChatLLM:
    return AnthropicChatLLM(client=client, model=model)  # type: ignore[arg-type]


def _api_error() -> anthropic.APIError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(message=_SECRET_DETAIL, request=request)


def test_yields_text_deltas_in_order() -> None:
    client = _FakeClient(["RSUs ", "are taxed ", "at vest [1]."])
    out = list(_llm(client).stream_answer(SYSTEM_PROMPT, "How are RSUs taxed?", _SOURCES))
    assert out == ["RSUs ", "are taxed ", "at vest [1]."]


def test_request_kwargs_shape() -> None:
    client = _FakeClient(["ok"])
    list(_llm(client, "claude-haiku-5-5").stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))

    (kwargs,) = client.messages.calls
    assert kwargs["model"] == "claude-haiku-5-5"
    assert isinstance(kwargs["max_tokens"], int) and kwargs["max_tokens"] > 0
    assert SYSTEM_PROMPT in str(kwargs["system"])
    assert kwargs["messages"] == [{"role": "user", "content": _build_user_message("Q?", _SOURCES)}]
    assert kwargs["output_config"] == {"effort": "low"}


def test_system_param_carries_the_passed_system_verbatim() -> None:
    client = _FakeClient(["ok"])
    list(_llm(client).stream_answer("custom system text", "Q?", _SOURCES))
    assert "custom system text" in str(client.messages.calls[0]["system"])


def test_never_sends_sampling_params() -> None:
    """Haiku 5.5 returns HTTP 400 for any non-default sampling parameter."""
    client = _FakeClient(["ok"])
    list(_llm(client).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))
    sent = client.messages.calls[0]
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in sent


def test_api_error_mid_stream_becomes_chat_completion_failed_without_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient(["partial "], error=_api_error())
    gen = _llm(client).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES)
    with caplog.at_level(logging.WARNING), pytest.raises(ChatCompletionFailedError) as info:
        list(gen)
    assert _SECRET_DETAIL not in str(info.value)
    assert _SECRET_DETAIL in caplog.text  # detail is logged for operators


def test_httpx_error_mid_stream_becomes_chat_completion_failed() -> None:
    err = httpx.ReadError(_SECRET_DETAIL)
    client = _FakeClient(["partial "], error=err)
    with pytest.raises(ChatCompletionFailedError) as info:
        list(_llm(client).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))
    assert _SECRET_DETAIL not in str(info.value)


def test_error_raised_when_opening_the_stream_is_also_converted() -> None:
    class _Boom(_FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.messages.stream = self._raise  # type: ignore[method-assign]

        @staticmethod
        def _raise(**_: Any) -> _FakeStream:
            raise _api_error()

    with pytest.raises(ChatCompletionFailedError):
        list(_llm(_Boom()).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))


def test_refusal_stop_reason_is_a_provider_failure() -> None:
    client = _FakeClient(["I can't"], stop_reason="refusal")
    with pytest.raises(ChatCompletionFailedError):
        list(_llm(client).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES))


def test_normal_stop_reasons_do_not_raise() -> None:
    for reason in ("end_turn", "max_tokens"):
        client = _FakeClient(["x"], stop_reason=reason)
        assert list(_llm(client).stream_answer(SYSTEM_PROMPT, "Q?", _SOURCES)) == ["x"]


def test_from_settings_uses_anthropic_key_and_chat_model() -> None:
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test-key",
        openai_api_key="sk-should-not-be-used",
        chat_model="claude-haiku-5-5",
    )
    llm = AnthropicChatLLM.from_settings(settings)
    assert llm._client.api_key == "sk-ant-test-key"
    assert llm._model == "claude-haiku-5-5"


def test_from_settings_falls_back_to_unset_when_key_empty() -> None:
    settings = Settings(llm_provider="anthropic", anthropic_api_key="", chat_model="m")
    llm = AnthropicChatLLM.from_settings(settings)
    assert llm._client.api_key == "unset"


def test_build_chat_llm_picks_anthropic_when_provider_is_anthropic() -> None:
    from app.rag.chat_provider import build_chat_llm

    settings = Settings(
        llm_provider="anthropic", anthropic_api_key="sk-ant-x", chat_model="claude-haiku-5-5"
    )
    assert isinstance(build_chat_llm(settings), AnthropicChatLLM)


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_build_chat_llm_picks_openai_compatible_otherwise(provider: str) -> None:
    from app.rag.chat_provider import build_chat_llm

    settings = Settings(llm_provider=provider, openai_api_key="sk-x", nvidia_api_key="nvapi-x")
    assert isinstance(build_chat_llm(settings), OpenAICompatibleChatLLM)


def test_main_wires_chat_llm_through_the_seam() -> None:
    """`app.main` must pick the provider via `build_chat_llm`, not call the OpenAI class directly
    (reads the source: importing `app.main` needs a live DATABASE_URL)."""
    source = (Path(__file__).parent.parent / "app" / "main.py").read_text()
    assert "build_chat_llm(settings)" in source
    assert "OpenAICompatibleChatLLM.from_settings" not in source
