"""Test-author (RED) file for Task K: the Claude-only style addendum (anthropic-haiku brief).

Claude answers ran ~2x longer than the baseline and carried standalone non-factual sentences that
a per-sentence groundedness judge marks unsupported. The fix lives ONLY in the Anthropic adapter:
`app.rag.anthropic_chat.CLAUDE_STYLE_ADDENDUM` is appended to the system text it is given
(`system + "\\n\\n" + CLAUDE_STYLE_ADDENDUM`). `SYSTEM_PROMPT` and the OpenAI path stay untouched.
No network: stub clients only (CONVENTIONS.md §10).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from types import TracebackType
from typing import Any

import httpx
from openai import OpenAI

from app.rag import anthropic_chat
from app.rag.anthropic_chat import AnthropicChatLLM
from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import SYSTEM_PROMPT, OpenAICompatibleChatLLM

_SYSTEM_PROMPT_SHA256 = "24f958abb57032dfd3ada09f034037adf6f108e6d13314835e6481f8af25269b"
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


class _FinalMessage:
    stop_reason = "end_turn"


class _FakeStream:
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
        yield "ok"

    def get_final_message(self) -> _FinalMessage:
        return _FinalMessage()


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        return _FakeStream()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _sent(system: str, *, effort: str | None = None) -> dict[str, Any]:
    client = _FakeClient()
    if effort is None:
        llm = AnthropicChatLLM(client=client, model="claude-haiku-5-5")  # type: ignore[arg-type]
    else:
        llm = AnthropicChatLLM(
            client=client,  # type: ignore[arg-type]
            model="claude-haiku-5-5",
            effort=effort,
        )
    list(llm.stream_answer(system, "Q?", _SOURCES))
    (kwargs,) = client.messages.calls
    return kwargs


def _addendum() -> str:
    return anthropic_chat.CLAUDE_STYLE_ADDENDUM


# ---- 1: constant + exact composition ------------------------------------------------------------


def test_addendum_is_a_non_empty_string() -> None:
    assert isinstance(_addendum(), str)
    assert _addendum().strip()


def test_system_is_given_text_then_blank_line_then_addendum() -> None:
    assert _sent("custom system text")["system"] == "custom system text\n\n" + _addendum()


def test_system_prompt_stays_first_and_unchanged_in_the_sent_system() -> None:
    sent = _sent(SYSTEM_PROMPT)["system"]
    assert sent.startswith(SYSTEM_PROMPT + "\n\n")
    assert sent.endswith(_addendum())


# ---- 2: content, pinned loosely -----------------------------------------------------------------


def test_addendum_limits_length_in_sentences() -> None:
    assert "sentence" in _addendum().lower()


def test_addendum_forbids_standalone_yes_no_and_bridging_sentences() -> None:
    text = _addendum().lower()
    assert "yes" in text
    assert "standalone" in text or "on its own" in text


def test_addendum_requires_a_citation_per_sentence() -> None:
    text = _addendum().lower()
    assert "cite" in text or "citation" in text


def test_addendum_does_not_grant_general_knowledge_permission() -> None:
    text = _addendum().lower()
    for phrase in (
        "you may use general knowledge",
        "you may draw on general knowledge",
        "you can use general knowledge",
        "feel free to use general knowledge",
    ):
        assert phrase not in text


# ---- 3: SYSTEM_PROMPT frozen; OpenAI path never carries the addendum ----------------------------


def test_system_prompt_is_unchanged() -> None:
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == _SYSTEM_PROMPT_SHA256


def test_openai_adapter_sends_system_verbatim_without_the_addendum() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, content=b"data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
        )

    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    llm = OpenAICompatibleChatLLM(client=client, model="gpt-4o-mini")
    list(llm.stream_answer("custom system text", "Q?", _SOURCES))

    system_message = captured["body"]["messages"][0]
    assert system_message["role"] == "system"
    assert system_message["content"] == "custom system text"
    assert _addendum() not in json.dumps(captured["body"])


# ---- 4: existing behaviors hold with the addendum present ---------------------------------------


def test_no_sampling_params_are_sent() -> None:
    kwargs = _sent(SYSTEM_PROMPT)
    assert _addendum() in kwargs["system"]
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in kwargs


def test_output_config_effort_comes_from_the_constructor() -> None:
    kwargs = _sent(SYSTEM_PROMPT, effort="medium")
    assert _addendum() in kwargs["system"]
    assert kwargs["output_config"] == {"effort": "medium"}
