"""Test-author (RED) file for task 6R-14 — the OpenAI-provider credential path for
`app.rag.synthesis.OpenAICompatibleChatLLM` (`app.agent.llm.OpenAICompatibleAgentLLM` shares the
exact same `from_settings` shape/pattern; this file covers the synthesis chat client, the
public-facing `/public/chat` path task-14's outage is actually about).

`docs/plans/phase-6-remediation/task-14-openai-provider-swap.md` (P0 production outage: both
pinned NVIDIA models are EOL/410 Gone). Design pin #3: "Chat (llm.py + synthesis.py):
`from_settings` uses `settings.llm_api_key`. No param change." — unlike the embedding client, the
chat-completions wire shape needs ZERO code change for the provider swap: `stream_answer` never
sent NVIDIA-specific `extra_body` in the first place (task-14: "The chat client... sends no
NVIDIA-specific params -> clean"). What changes is only WHICH `Settings` field `from_settings`
reads the API key from.

Mirrors `tests/test_chat_llm_client.py`'s `_chat_llm_with_transport`/`_sse_chunk`/`_stream_response`
technique exactly (`httpx.MockTransport`, zero network — CONVENTIONS.md §10). This is a NEW file,
not an edit to that pinned one (task-14 test-author scope: "a wire test confirming the chat
client authenticates with the OpenAI key... (extend the existing pattern in a NEW file)") —
`test_chat_llm_client.py` itself needs no edits: none of its existing tests assert on `.api_key`,
so nothing there breaks once the credential resolution changes underneath.

RED (current HEAD, pre-implementation): `llm_provider`/`openai_api_key`/`llm_api_key` don't exist
on `Settings` yet, so every `Settings(llm_provider=..., openai_api_key=...)` call below raises
`pydantic_core.ValidationError` (`extra_forbidden`) at CALL time, inside the test body — never at
collection time (`OpenAICompatibleChatLLM`/`Settings` both already exist and import fine today).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from openai import OpenAI

from app.config import Settings
from app.rag.synthesis import OpenAICompatibleChatLLM


def _chat_llm_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str = "gpt-4o-mini",
    max_retries: int = 0,
) -> OpenAICompatibleChatLLM:
    """Build a real `OpenAICompatibleChatLLM` wired to a fake HTTP transport — no network.
    Mirrors `test_chat_llm_client.py::_chat_llm_with_transport` exactly.
    """
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=max_retries,
    )
    return OpenAICompatibleChatLLM(client=client, model=model)


def _sse_chunk(*, content: str | None = None) -> dict[str, object]:
    """One well-formed `chat.completion.chunk` payload — mirrors
    `test_chat_llm_client.py::_sse_chunk` (trimmed to what these tests need)."""
    delta: dict[str, str] = {}
    if content is not None:
        delta["content"] = content
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }


def _stream_response(events: list[dict[str, object] | None]) -> httpx.Response:
    """A well-formed streaming `/v1/chat/completions` 200 response body — mirrors
    `test_chat_llm_client.py::_stream_response`/`_sse_body`."""
    lines = [f"data: {'[DONE]' if event is None else json.dumps(event)}\n\n" for event in events]
    return httpx.Response(
        200, content="".join(lines).encode(), headers={"content-type": "text/event-stream"}
    )


# ---- from_settings: resolves the OpenAI key via settings.llm_api_key ---------------------------


def test_from_settings_uses_the_openai_key_when_provider_is_openai() -> None:
    """Design pin #3: `from_settings` builds the client with `settings.llm_api_key` — under the
    default `llm_provider="openai"`, that must be `settings.openai_api_key`, NOT
    `settings.nvidia_api_key` (task-14: "the credential field `nvidia_api_key`... is used for
    BOTH [chat and embedding] and must pick up the OpenAI key" — via the new `llm_api_key`
    property).
    """
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test-openai-key",
        nvidia_api_key="nvapi-should-not-be-used",
        chat_model="gpt-4o-mini",
    )

    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)

    assert chat_llm._client.api_key == "sk-test-openai-key"
    assert chat_llm._model == "gpt-4o-mini"


def test_from_settings_falls_back_to_the_nvidia_key_when_provider_is_nvidia() -> None:
    """The back-compat branch: `llm_provider="nvidia"` still resolves the client's API key to
    `settings.nvidia_api_key`, exactly as `OpenAICompatibleChatLLM.from_settings` behaved before
    this task."""
    settings = Settings(
        llm_provider="nvidia",
        openai_api_key="sk-should-not-be-used",
        nvidia_api_key="nvapi-test-key",
    )

    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)

    assert chat_llm._client.api_key == "nvapi-test-key"


def test_from_settings_falls_back_to_unset_api_key_when_openai_api_key_is_empty() -> None:
    """Dev-mode boot-safety, extended to the OpenAI branch (mirrors
    `OpenAICompatibleEmbedder.from_settings`'s own empty-key handling, task-14 design pin #1:
    "The empty-key... boot-safety fallback pattern stays"): an empty `openai_api_key` under the
    default `llm_provider="openai"` must not crash `from_settings` — the `openai` SDK raises at
    *construction* time for a falsy `api_key` with no `OPENAI_API_KEY` env var either, which
    would crash `app.main`'s module-level wiring on every offline dev boot.
    """
    settings = Settings(llm_provider="openai", openai_api_key="")

    chat_llm = OpenAICompatibleChatLLM.from_settings(settings)

    assert chat_llm._client.api_key == "unset"


def test_from_settings_uses_the_openai_default_chat_model() -> None:
    """A zero-env-var `Settings()` (defaults now OpenAI, task-14 design pin #1) round-trips onto
    the chat client built from it: `gpt-4o-mini`.
    """
    chat_llm = OpenAICompatibleChatLLM.from_settings(Settings())

    assert chat_llm._model == "gpt-4o-mini"


# ---- Wire shape: standard chat-completions, no NVIDIA extra_body (design pin #3: "no change") --


def test_openai_provider_chat_completions_wire_shape_carries_no_nvidia_extra_body() -> None:
    """Confirms design pin #3's "no param change" empirically: a chat client built for the
    OpenAI provider (an OpenAI model name, an OpenAI-shaped key) still sends EXACTLY
    `{"model", "messages", "stream"}` on the wire — no `input_type`/`truncate`/any other
    NVIDIA-only key — because `stream_answer` never branches on provider at all. This is the
    counterpart to `test_chat_llm_client.py`'s own `test_request_body_carries_only_model_
    messages_stream_no_extra_body` pin, framed explicitly for the OpenAI provider this task
    introduces.
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return _stream_response([_sse_chunk(content="Hi"), None])

    chat_llm = _chat_llm_with_transport(handler, model="gpt-4o-mini")

    list(chat_llm.stream_answer("SYSTEM PROMPT", "What is a Roth IRA?", ()))

    assert captured["url"] == "https://fake-provider.example/v1/chat/completions"
    body = captured["body"]
    assert isinstance(body, dict)
    assert set(body.keys()) == {"model", "messages", "stream"}
    assert body["model"] == "gpt-4o-mini"
    assert body["stream"] is True
