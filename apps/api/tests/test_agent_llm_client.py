"""Fixer-owned tests for `app.agent.llm.OpenAICompatibleAgentLLM` (phase-5 task-03 review round
1, finding I-2).

Task: /home/ak/Documents/github_akanksha/AdvisorDesk/.superpowers/sdd/reports/p5-t03-review.md
(Opus review of commit `e58f007`). Mirrors `tests/test_chat_llm_client.py`'s technique exactly
(`OpenAICompatibleChatLLM`'s own review-round-1 fixer file, itself mirroring
`tests/test_embeddings_client.py`): exercises the real `OpenAICompatibleAgentLLM` (the real
`openai` SDK client) against a fake HTTP transport (`httpx.MockTransport`) — zero-network, but
proves what actually goes on the wire, how a response maps to an `LlmStep`, and how the fix-round
findings that live specifically in THIS module are pinned:

  - **C-2**: a text-only response (no `tool_calls`) is the model's FINAL message — `next_step`
    returns `TextDelta` for it, then `LlmDone()` on the very next call with NO further provider
    call (`test_text_only_response_terminates_...`).
  - **C-3**: `_pending_tool_calls`/the "turn finished" flag are per-conversation state —
    `new_conversation()` returns a FRESH instance that never sees another conversation's leftover
    queue (`test_fresh_conversation_...`).
  - **C-1** (wire-shape confirmation — the loop-level fix itself is pinned in
    `tests/test_agent_loop_guards.py`): `next_step` passes `messages` through to the SDK
    UNCHANGED — a synthesized tool-call message already carrying `arguments` as a JSON string
    (what `app.agent.loop.run_agent` now produces) reaches the real HTTP request body as that
    same string, never re-wrapped (`test_json_string_arguments_pass_through_...`).
  - Tool-call mapping, including a malformed-JSON `arguments` string from the provider handled
    gracefully (never a raw `json.JSONDecodeError` escaping to the caller).
  - The `"unset"` boot-safe fallback and provider errors logged, never enveloped (mirrors
    `test_chat_llm_client.py`'s own R8 pins).
  - Binding rule 3's C-2/C-3 composite (`test_two_sequential_agent_chat_requests_...`, at the
    bottom): drives the FULL production wiring (`create_app(agent_llm_factory=...)` ->
    `app.routes.deps.get_agent_llm` -> `POST /agent/chat`) through TWO sequential real HTTP
    requests over ONE app, proving request isolation end to end (not just at the adapter-unit
    level the tests above cover).

`app/agent/llm.py` had ZERO test coverage before this file (I-2) — two of the four Criticals in
the review (C-2, C-3) live exactly here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import httpx
import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy import Engine

from app.agent.llm import (
    AgentLLMFailedError,
    OpenAICompatibleAgentLLM,
    _to_openai_tools,
)
from app.agent.loop import LlmDone, TextDelta, ToolCallStep
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app

_TOOL_SCHEMAS = [
    {
        "name": "search_content",
        "description": "Search CMS content.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    },
    {
        "name": "count_content",
        "description": "Count CMS content.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

_MESSAGES = [
    {"role": "system", "content": "SYSTEM PROMPT"},
    {"role": "user", "content": "How many published pieces are there?"},
]


def _agent_llm_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
) -> OpenAICompatibleAgentLLM:
    """Build a real `OpenAICompatibleAgentLLM` wired to a fake HTTP transport — no network.

    Mirrors `test_chat_llm_client.py::_chat_llm_with_transport` exactly.
    """
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=max_retries,
    )
    return OpenAICompatibleAgentLLM(client=client, model="test-agent-model")


def _completion_response(
    *,
    tool_calls: list[tuple[str, dict[str, object]]] | None = None,
    content: str | None = None,
    raw_arguments: list[str] | None = None,
) -> httpx.Response:
    """One well-formed (or, via `raw_arguments`, deliberately malformed) non-streaming
    `chat.completion` response body.

    `raw_arguments`, when given, overrides each tool call's `function.arguments` with the raw
    string supplied (bypassing `json.dumps`) — used to simulate a malformed/non-JSON arguments
    string from the provider itself.
    """
    message: dict[str, object] = {"role": "assistant", "content": content}
    finish_reason = "stop"
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": (
                        raw_arguments[i - 1] if raw_arguments is not None else json.dumps(args)
                    ),
                },
            }
            for i, (name, args) in enumerate(tool_calls, start=1)
        ]
        finish_reason = "tool_calls"
    body = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-agent-model",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }
    return httpx.Response(200, json=body)


# ---- Request shape: model/messages/tools/tool_choice, no extra_body ----------------------------


def test_request_body_carries_model_messages_tools_tool_choice_no_extra_body() -> None:
    """The actual HTTP request body must be exactly `{"model", "messages", "tools",
    "tool_choice", "temperature"}` — no NVIDIA-specific `extra_body` — `tool_choice` must be
    `"auto"` (the probe-derived pin: the pinned model over-calls tools without the loop's own
    steering line, but `tool_choice` itself must still be `"auto"`, not `"required"`/a forced
    single tool), and `temperature` must be `0` (checkpoint fix: provider-default sampling made
    tool SELECTION nondeterministic across identical commands; every qualifying probe ran at
    0)."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return _completion_response(content="Text answer.")

    agent_llm = _agent_llm_with_transport(handler)

    agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert captured["url"] == "https://fake-provider.example/v1/chat/completions"
    body = captured["body"]
    assert isinstance(body, dict)
    assert set(body.keys()) == {"model", "messages", "tools", "tool_choice", "temperature"}
    assert body["model"] == "test-agent-model"
    assert body["tool_choice"] == "auto"
    assert body["temperature"] == 0
    assert body["messages"] == _MESSAGES


def test_to_openai_tools_adapts_registry_schema_shape_to_openai_function_tools() -> None:
    """`_to_openai_tools` adapts `list_tool_schemas()`'s `{"name","description","inputSchema"}`
    shape into `[{"type":"function","function":{"name","description","parameters"}}]` — done in
    THIS module (not the loop), per the brief's own "adapt in the LLM implementation" pin."""
    adapted = _to_openai_tools(_TOOL_SCHEMAS)

    assert adapted == [
        {
            "type": "function",
            "function": {
                "name": "search_content",
                "description": "Search CMS content.",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "count_content",
                "description": "Count CMS content.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def test_json_string_arguments_pass_through_to_the_wire_unchanged() -> None:
    """C-1 wire-shape confirmation: `next_step` passes `messages` to the SDK with NO reshaping.
    `app.agent.loop.run_agent`'s own fix (pinned directly in
    `tests/test_agent_loop_guards.py`) synthesizes a tool-call message whose
    `function.arguments` is already a JSON-encoded STRING before handing it back to
    `next_step` — this asserts that string reaches the real HTTP request body byte-for-byte,
    never re-wrapped into a dict or re-encoded."""
    synthesized_arguments = json.dumps({"title": "Roth IRA Basics", "tags": ["retirement"]})
    messages_with_synthesized_tool_call = [
        *_MESSAGES,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "create_draft", "arguments": synthesized_arguments},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "{'id': '...'}"},
    ]
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _completion_response(content="Done.")

    agent_llm = _agent_llm_with_transport(handler)

    agent_llm.next_step(messages_with_synthesized_tool_call, _TOOL_SCHEMAS)

    body = captured["body"]
    assert isinstance(body, dict)
    sent_messages = body["messages"]
    assert isinstance(sent_messages, list)
    sent_tool_call_message = next(m for m in sent_messages if m.get("tool_calls"))
    wire_arguments = sent_tool_call_message["tool_calls"][0]["function"]["arguments"]
    assert isinstance(wire_arguments, str)
    assert wire_arguments == synthesized_arguments


# ---- Tool-call mapping ---------------------------------------------------------------------


def test_tool_call_response_maps_to_tool_call_step_with_arguments_parsed_from_json_string() -> None:
    """A `tool_calls` response maps to `ToolCallStep(name, arguments)` — `arguments` parsed
    back from the wire's JSON string into a real dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _completion_response(tool_calls=[("search_content", {"q": "roth ira"})])

    agent_llm = _agent_llm_with_transport(handler)

    step = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.name == "search_content"
    assert step.arguments == {"q": "roth ira"}


def test_parallel_tool_calls_drain_in_order_without_requerying_the_provider() -> None:
    """A single completion carrying MULTIPLE `tool_calls` (parallel tool calls) surfaces the
    first as a `ToolCallStep`; the rest drain one at a time on later `next_step` calls with NO
    further provider call."""
    handler_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        return _completion_response(
            tool_calls=[
                ("search_content", {"q": "a"}),
                ("count_content", {}),
                ("search_content", {"q": "b"}),
            ]
        )

    agent_llm = _agent_llm_with_transport(handler)

    step1 = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    step2 = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    step3 = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert len(handler_calls) == 1, "only the FIRST next_step call queries the provider"
    assert isinstance(step1, ToolCallStep) and step1.name == "search_content"
    assert step1.arguments == {"q": "a"}
    assert isinstance(step2, ToolCallStep) and step2.name == "count_content"
    assert isinstance(step3, ToolCallStep) and step3.name == "search_content"
    assert step3.arguments == {"q": "b"}


def test_malformed_json_arguments_from_the_provider_raise_agent_llm_failed_error_not_json_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """I-2: a malformed/non-JSON `arguments` string from the provider (real providers do send
    truncated/invalid JSON occasionally) must become `AgentLLMFailedError`, never a raw
    `json.JSONDecodeError` escaping to `run_agent`. Handled by the SAME
    `except (..., json.JSONDecodeError)` clause every other provider failure goes through —
    logged for operators, never placed on the client-facing message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _completion_response(
            tool_calls=[("search_content", {"q": "irrelevant"})],
            raw_arguments=["{not valid json!!"],
        )

    agent_llm = _agent_llm_with_transport(handler)

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        with pytest.raises(AgentLLMFailedError) as exc_info:
            agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert str(exc_info.value) == "The agent LLM provider call failed."
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)
    warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("agent LLM provider call failed" in message for message in warnings)


# ---- C-2: text-only response terminates the exchange -------------------------------------------


def test_text_only_response_terminates_on_the_next_call_with_no_further_provider_call() -> None:
    """Fix round 1, finding C-2: a completion with `content` and no `tool_calls` IS the model's
    final message. The FIRST `next_step` call returns `TextDelta`; the SECOND call (same
    instance — `run_agent` re-queries once more after appending the text) must return
    `LlmDone()` with ZERO further HTTP calls to the transport — proving the exchange actually
    terminates instead of re-querying forever (the pre-fix bug: `LlmDone` was unreachable in
    production because a text answer always has non-empty `content`)."""
    handler_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        if len(handler_calls) > 1:
            raise AssertionError(
                "the provider must be queried exactly ONCE for a text-only exchange — a second "
                "call means the loop never terminated"
            )
        return _completion_response(content="You can search, create, edit, and publish content.")

    agent_llm = _agent_llm_with_transport(handler)

    step1 = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    step2 = agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step1, TextDelta)
    assert step1.text == "You can search, create, edit, and publish content."
    assert isinstance(step2, LlmDone)
    assert len(handler_calls) == 1


# ---- C-3: fresh-per-request isolation -----------------------------------------------------------


def test_fresh_conversation_leaves_no_pending_state_for_the_next_one() -> None:
    """Fix round 1, finding C-3 (reproduced live against the real provider, probe P-E): a
    process-lifetime singleton's `_pending_tool_calls` leaked a still-queued parallel tool call
    into the NEXT admin's unrelated request. `new_conversation()` returns a FRESH instance
    sharing only the `client`/`model` — this proves a SECOND conversation's first `next_step`
    call actually queries the provider (a real request), rather than silently draining the
    FIRST conversation's leftover queue with zero provider calls."""
    handler_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        if len(handler_calls) == 1:
            # "Request 1": three parallel tool calls — cap-truncated after the first attempt
            # (this test never drains #2/#3), mirroring the reviewer's exact scenario ("a
            # cap-truncated first request leaves nothing queued for the second").
            return _completion_response(
                tool_calls=[
                    ("search_content", {"q": "x"}),
                    ("count_content", {}),
                    ("search_content", {"q": "y"}),
                ]
            )
        # "Request 2": a distinct single tool call — must be reached via a REAL provider call.
        return _completion_response(tool_calls=[("count_content", {})])

    builder = _agent_llm_with_transport(handler)

    conversation1 = builder.new_conversation()
    step1 = conversation1.next_step(_MESSAGES, _TOOL_SCHEMAS)
    assert isinstance(step1, ToolCallStep) and step1.name == "search_content"
    assert step1.arguments == {"q": "x"}
    # `conversation1` still has 2 queued tool calls it never drained — simulating the cap firing
    # (or a graceful `Error`) after the first attempt in request 1. It is never touched again.

    conversation2 = builder.new_conversation()
    assert conversation2 is not conversation1

    step2 = conversation2.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert len(handler_calls) == 2, "request 2 must issue its OWN provider call"
    assert isinstance(step2, ToolCallStep)
    assert step2.name == "count_content"
    assert step2.arguments == {}, "must NOT be conversation1's leftover 'count_content' queue item"


# ---- Provider failures: logged, never enveloped --------------------------------------------


def test_non_2xx_response_yields_fixed_message_not_raw_provider_text() -> None:
    """A 401 (bad/rotated key) must raise `AgentLLMFailedError` with the fixed, generic message
    — never the provider's raw response text (mirrors `test_chat_llm_client.py`'s R8 pin)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "sk-secret-detail-leak", "type": "invalid_api_key"}}
        )

    agent_llm = _agent_llm_with_transport(handler)

    with pytest.raises(AgentLLMFailedError) as exc_info:
        agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    message = str(exc_info.value)
    assert message == "The agent LLM provider call failed."
    assert "sk-secret-detail-leak" not in message
    assert exc_info.value.code == "agent_llm_failed"


def test_provider_error_is_logged_and_chained_via_from_exc(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The raw provider detail isn't lost, just kept out of the client-facing message: it's
    logged (`logger.warning`) for operators, and the original exception is still chained
    (`raise ... from exc`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "sk-secret-detail-leak", "type": "invalid_api_key"}}
        )

    agent_llm = _agent_llm_with_transport(handler)

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        with pytest.raises(AgentLLMFailedError) as exc_info:
            agent_llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert exc_info.value.__cause__ is not None
    assert "sk-secret-detail-leak" in str(exc_info.value.__cause__)
    warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("sk-secret-detail-leak" in message for message in warnings)


# ---- from_settings: "unset" fallback + timeout/retry reuse --------------------------------------


def test_from_settings_falls_back_to_unset_api_key_when_nvidia_api_key_is_empty() -> None:
    """Dev-mode boot-safety (mirrors `OpenAICompatibleChatLLM`/`OpenAICompatibleEmbedder`): an
    empty `nvidia_api_key` must not crash `from_settings` — the `openai` SDK raises at
    *construction* time for a falsy `api_key` with no `OPENAI_API_KEY` env var either, which
    would crash `app.main`'s module-level wiring on every offline dev boot.

    Task 6R-14 pre-authorized pinned edit: explicit `llm_provider="nvidia"` — `from_settings`
    now resolves its API key via `settings.llm_api_key` (openai when `llm_provider="openai"`,
    the new default), so this test must pin the NVIDIA branch explicitly to keep testing what
    its name says: an empty `nvidia_api_key` under the `nvidia` provider still boot-safes to
    `"unset"`. The `provider="openai"` empty-key case is covered separately, in
    `tests/test_openai_embeddings_wire.py`'s/the new chat-wire file's own boot-safety pins.
    """
    settings = Settings(llm_provider="nvidia", nvidia_api_key="")

    agent_llm = OpenAICompatibleAgentLLM.from_settings(settings)

    assert agent_llm._client.api_key == "unset"


def test_from_settings_reuses_embedding_timeout_and_max_retries() -> None:
    """`from_settings` applies `Settings.embedding_timeout_seconds`/`embedding_max_retries` to
    the real client (mirrors `OpenAICompatibleChatLLM.from_settings`'s own documented reuse
    decision — no dedicated `AGENT_*`/`CHAT_*` settings exist).

    Task 6R-14 pre-authorized pinned edit: explicit `llm_provider="nvidia"` alongside the
    `nvidia_api_key` this test sets — makes the NVIDIA configuration this test exercises
    unambiguous now that `llm_provider` (default `"openai"`) governs which key `from_settings`
    actually reads (this particular test never asserts on `.api_key`, so it was not at risk of
    silently breaking, but gating it keeps every `nvidia_api_key=`-setting test in this file
    consistent).
    """
    settings = Settings(
        llm_provider="nvidia",
        nvidia_api_key="test-nvidia-key",
        embedding_timeout_seconds=12.5,
        embedding_max_retries=5,
        chat_model="test-agent-model",
    )

    agent_llm = OpenAICompatibleAgentLLM.from_settings(settings)

    assert agent_llm._client.timeout == 12.5
    assert agent_llm._client.max_retries == 5
    assert agent_llm._model == "test-agent-model"


def test_new_conversation_shares_client_and_model_with_the_builder() -> None:
    """`new_conversation()` returns a DIFFERENT instance that shares the same underlying
    `client`/`model` (cheap to construct, no new HTTP client/connection pool per request)."""
    agent_llm = OpenAICompatibleAgentLLM.from_settings(Settings(nvidia_api_key="test-key"))

    conversation = agent_llm.new_conversation()

    assert conversation is not agent_llm
    assert conversation._client is agent_llm._client
    assert conversation._model == agent_llm._model
    assert conversation._pending_tool_calls == []
    assert conversation._finished is False


# ---- Binding rule 3: C-2/C-3 composite, through the REAL production wiring --------------------


def _build_settings() -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails="agent-llm-admin@example.com",
    )


def test_two_sequential_agent_chat_requests_through_one_app_show_no_cross_request_state_leak(
    tmp_engine: Engine,
) -> None:
    """Fix round 1, C-2/C-3 composite (binding rule 3): TWO sequential `/agent/chat` exchanges
    through ONE real `create_app(agent_llm_factory=...)` app — not the loop-level `FakeAgentLLM`
    seam `tests/test_agent_endpoint.py` uses, but the actual production request-isolation
    mechanism (`app.routes.deps.get_agent_llm` calling the factory fresh per request).

    Request 1's single provider turn returns TEN parallel `count_content` tool calls; the loop's
    own §6 cap (`_MAX_TOOL_CALLS=8`, fix round 1 finding I-1) fires after the 8th ATTEMPT,
    leaving 2 calls still queued, undrained, on request 1's `OpenAICompatibleAgentLLM` instance
    — exactly the reviewer's own scenario ("a cap-truncated first request leaves nothing queued
    for the second", probe P-E). Request 2 asks an unrelated question; it must get its OWN fresh
    provider call and answer, never silently execute one of request 1's leftover queued tool
    calls with zero provider calls.
    """
    handler_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        if len(handler_calls) == 1:
            return _completion_response(tool_calls=[("count_content", {}) for _ in range(10)])
        return _completion_response(content="There are 0 published pieces.")

    agent_llm_builder = _agent_llm_with_transport(handler)
    session_factory = make_session_factory(tmp_engine)
    app = create_app(
        session_factory=session_factory,
        settings=_build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
        agent_llm_factory=agent_llm_builder.new_conversation,
    )
    client = TestClient(app)
    login_as(client, "agent-llm-admin@example.com")

    with client.stream(
        "POST",
        "/api/v1/agent/chat",
        json={"messages": [{"role": "user", "content": "Count the content ten times over."}]},
    ) as response1:
        body1 = "".join(response1.iter_text())
    assert response1.status_code == 200, body1
    assert body1.count("event: tool_call") == 8, "the cap must stop request 1 at 8 ATTEMPTS"
    assert "event: done" in body1

    with client.stream(
        "POST",
        "/api/v1/agent/chat",
        json={"messages": [{"role": "user", "content": "How many pieces are published?"}]},
    ) as response2:
        body2 = "".join(response2.iter_text())
    assert response2.status_code == 200, body2

    assert len(handler_calls) == 2, "request 2 must issue its OWN fresh provider call"
    assert "event: tool_call" not in body2, (
        "request 2 must NOT silently execute one of request 1's leftover queued tool calls"
    )
    assert "There are 0 published pieces." in body2
