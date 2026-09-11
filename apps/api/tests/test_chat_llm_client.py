"""Fixer-owned tests for `app.rag.synthesis.OpenAICompatibleChatLLM` (phase-4 task-02 review
round 1, finding I-2).

Mirrors `tests/test_embeddings_client.py`'s technique exactly (`OpenAICompatibleEmbedder`'s own
review-round-1 fixer file): exercises the real `OpenAICompatibleChatLLM` (the real `openai` SDK
client) against a fake HTTP transport (`httpx.MockTransport`), so it's zero-network but proves
what request actually goes on the wire, how streamed chunks decode, and how failures — at request
time AND mid-stream — become `ChatCompletionFailedError`.

`tests/test_public_chat.py` (pinned) never constructs a real `OpenAICompatibleChatLLM` at all —
every route test fakes the `ChatLLM` seam (`FakeChatLLM`) — so this class had zero coverage before
this file (implementer self-flagged; reviewer's probes P11-P16 confirmed the gap was load-bearing,
not ceremonial: `except OpenAIError` alone let `httpx.ReadError`/`json.JSONDecodeError` escape
mid-stream unconverted, contradicting `stream_answer`'s own `Raises:` contract).

Covers:
  - I-2: a mid-stream `httpx` transport failure (a dropped connection) and a malformed/truncated
    SSE chunk (a raw `json.JSONDecodeError` from the SDK's own decoder) both become
    `ChatCompletionFailedError`, not an unconverted third-party exception (probes P14/P15).
  - R7 (already true, pinned here too): the actual request body carries exactly
    `{"model", "messages", "stream"}` — no NVIDIA-specific `extra_body` (`input_type`/`truncate`
    are embedding-only NIM extras, PRD §7.2) — and streamed token deltas decode in order,
    including the role-only/empty-delta/usage-only chunk shapes real providers send.
  - R8: a non-2xx provider response also becomes `ChatCompletionFailedError` with the fixed,
    generic message — the raw provider response text never reaches it (only the log).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable

import httpx
import pytest
from openai import OpenAI

from app.config import Settings
from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import ChatCompletionFailedError, OpenAICompatibleChatLLM


def _chat_llm_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
) -> OpenAICompatibleChatLLM:
    """Build a real `OpenAICompatibleChatLLM` wired to a fake HTTP transport — no network.

    `max_retries=0` by default so an error-path test doesn't sit through the SDK's real retry
    backoff, mirroring `test_embeddings_client.py::_embedder_with_transport`.
    """
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=max_retries,
    )
    return OpenAICompatibleChatLLM(client=client, model="test-chat-model")


def _sse_chunk(
    *, role: str | None = None, content: str | None = None, finish_reason: str | None = None
) -> dict[str, object]:
    """One well-formed `chat.completion.chunk` payload (the JSON a real provider's SSE `data:`
    line carries).
    """
    delta: dict[str, str] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-chat-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _sse_body(events: list[dict[str, object] | None]) -> bytes:
    """Render `events` as an SSE byte body — `None` renders the terminal `data: [DONE]` line."""
    lines = []
    for event in events:
        data = "[DONE]" if event is None else json.dumps(event)
        lines.append(f"data: {data}\n\n")
    return "".join(lines).encode()


def _stream_response(events: list[dict[str, object] | None]) -> httpx.Response:
    """A well-formed streaming `/v1/chat/completions` 200 response body carrying `events`."""
    return httpx.Response(
        200, content=_sse_body(events), headers={"content-type": "text/event-stream"}
    )


_ONE_SOURCE = (
    RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content_id=uuid.uuid4(),
        title="Roth IRA Basics",
        slug="roth-ira-basics",
        text="Roth IRAs grow tax-free.",
        similarity=0.9,
    ),
)


# ---- R7: request shape — no NVIDIA extra_body, correct model/messages/stream -------------------


def test_request_body_carries_only_model_messages_stream_no_extra_body() -> None:
    """The actual HTTP request body must be exactly `{"model", "messages", "stream"}` — no
    `input_type`/`truncate` (those are `/v1/embeddings`-only NIM extras, PRD §7.2) — and
    `messages` must be `[system, user]` with the numbered context block + question in the user
    turn.
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return _stream_response([_sse_chunk(role="assistant"), _sse_chunk(content="Hi"), None])

    chat_llm = _chat_llm_with_transport(handler)

    list(chat_llm.stream_answer("SYSTEM PROMPT TEXT", "What is a Roth IRA?", _ONE_SOURCE))

    assert captured["url"] == "https://fake-provider.example/v1/chat/completions"
    body = captured["body"]
    assert isinstance(body, dict)
    # closeout 2026-09-11: `temperature` joined the wire shape (pinned to 0 so answers are
    # deterministic — the phase-7 groundedness baseline was noise at the default 1.0).
    assert set(body.keys()) == {"model", "messages", "stream", "temperature"}
    assert body["temperature"] == 0
    assert body["model"] == "test-chat-model"
    assert body["stream"] is True
    messages = body["messages"]
    assert isinstance(messages, list)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == "SYSTEM PROMPT TEXT"
    user_content = messages[1]["content"]
    assert "[1] Roth IRAs grow tax-free." in user_content
    assert "Question: What is a Roth IRA?" in user_content


def test_zero_sources_render_the_no_context_placeholder_in_the_user_message() -> None:
    """The refusal-path shape (PRD §7.4/§7.5): zero sources still produce a well-formed user
    message, with the documented placeholder text instead of an empty `[n]` list.
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _stream_response([_sse_chunk(content="No guidance."), None])

    chat_llm = _chat_llm_with_transport(handler)

    list(chat_llm.stream_answer("SYSTEM", "An uncovered question.", ()))

    body = captured["body"]
    assert isinstance(body, dict)
    user_content = body["messages"][1]["content"]
    assert "(no context chunks were retrieved for this question)" in user_content


# ---- R7 continued: streamed token decoding, including real-provider chunk shapes ---------------


def test_streamed_tokens_decode_in_order_skipping_role_only_and_usage_only_chunks() -> None:
    """A realistic stream — role-only opening chunk, an empty-string delta, real content chunks,
    and a usage-only final chunk with `choices == []` — must yield only the real text fragments,
    in order, with nothing skipped or duplicated (probe P11's exact shape).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _stream_response(
            [
                _sse_chunk(role="assistant"),
                _sse_chunk(content=""),
                _sse_chunk(content="Roth "),
                _sse_chunk(content="IRAs "),
                _sse_chunk(content="grow tax-free [1]."),
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test-chat-model",
                    "choices": [],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                _sse_chunk(finish_reason="stop"),
                None,
            ]
        )

    chat_llm = _chat_llm_with_transport(handler)

    tokens = list(chat_llm.stream_answer("SYSTEM", "question", _ONE_SOURCE))

    assert tokens == ["Roth ", "IRAs ", "grow tax-free [1]."]


# ---- R8 / I-2: request-time and mid-stream failures all become ChatCompletionFailedError -------


def test_non_2xx_response_yields_fixed_message_not_raw_provider_text() -> None:
    """A 401 (bad/rotated key) must raise `ChatCompletionFailedError` with the fixed, generic
    message — never the provider's raw response text (mirrors
    `test_embeddings_client.py`'s F6/M6 pin for the embedding client).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "sk-secret-detail-leak", "type": "invalid_api_key"}}
        )

    chat_llm = _chat_llm_with_transport(handler)

    with pytest.raises(ChatCompletionFailedError) as exc_info:
        list(chat_llm.stream_answer("SYSTEM", "question", ()))

    message = str(exc_info.value)
    assert message == "The chat completion provider call failed."
    assert "sk-secret-detail-leak" not in message
    assert exc_info.value.code == "chat_completion_failed"


def test_provider_error_is_logged_and_chained_via_from_exc(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The raw provider detail isn't lost, just kept out of the client-facing message: it's
    logged (`logger.warning`) for operators, and the original exception is still chained
    (`raise ... from exc`) — mirrors `test_embeddings_client.py`'s same pin for the embedding
    client.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "sk-secret-detail-leak", "type": "invalid_api_key"}}
        )

    chat_llm = _chat_llm_with_transport(handler)

    with caplog.at_level(logging.WARNING, logger="app.rag.synthesis"):
        with pytest.raises(ChatCompletionFailedError) as exc_info:
            list(chat_llm.stream_answer("SYSTEM", "question", ()))

    assert exc_info.value.__cause__ is not None
    assert "sk-secret-detail-leak" in str(exc_info.value.__cause__)
    warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("sk-secret-detail-leak" in message for message in warnings)


def test_mid_stream_transport_drop_raises_chat_completion_failed_error_not_httpx_error() -> None:
    """I-2 (probe P15): a connection reset PARTWAY through an already-open stream — a real
    `httpx.ReadError`, not a request-time failure — must also become `ChatCompletionFailedError`,
    not escape as a raw `httpx` exception. The previous `except OpenAIError`-only clause let this
    through unconverted; this is the regression pin for that gap.
    """

    class _DroppingStream(httpx.SyncByteStream):
        """Yields one well-formed SSE chunk, then raises mid-iteration — simulates a connection
        reset after the stream has already started (never on the very first read).
        """

        def __iter__(self) -> object:
            yield _sse_body([_sse_chunk(content="Partial ")])
            raise httpx.ReadError("connection reset by peer")

        def close(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=_DroppingStream(), headers={"content-type": "text/event-stream"}
        )

    chat_llm = _chat_llm_with_transport(handler)

    with pytest.raises(ChatCompletionFailedError) as exc_info:
        list(chat_llm.stream_answer("SYSTEM", "question", ()))

    assert str(exc_info.value) == "The chat completion provider call failed."
    assert isinstance(exc_info.value.__cause__, httpx.ReadError)


def test_mid_stream_malformed_chunk_raises_chat_completion_failed_error_not_json_error() -> None:
    """I-2 (probe P14): a truncated/malformed `data:` line partway through the stream raises a
    raw `json.JSONDecodeError` inside the SDK's own SSE decoder — must also become
    `ChatCompletionFailedError`, not escape as the raw decode error.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            f"data: {json.dumps(_sse_chunk(content='Partial '))}\n\ndata: {{not valid json!!\n\n"
        ).encode()
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    chat_llm = _chat_llm_with_transport(handler)

    with pytest.raises(ChatCompletionFailedError) as exc_info:
        list(chat_llm.stream_answer("SYSTEM", "question", ()))

    assert str(exc_info.value) == "The chat completion provider call failed."
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


# ---- from_settings: mirrors test_embeddings_client.py's F1/I1 timeout/retry pin ----------------


def test_from_settings_reuses_embedding_timeout_and_max_retries() -> None:
    """`from_settings` applies `Settings.embedding_timeout_seconds`/`embedding_max_retries` to the
    real client (the implementer's documented reuse decision — no dedicated `CHAT_*` settings
    exist), mirroring `OpenAICompatibleEmbedder`'s own client budget.
    """
    settings = Settings(
        nvidia_api_key="test-nvidia-key",
        embedding_timeout_seconds=12.5,
        embedding_max_retries=5,
        chat_model="test-chat-model",
    )

    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)

    assert chat_llm._client.timeout == 12.5
    assert chat_llm._client.max_retries == 5
    assert chat_llm._model == "test-chat-model"
