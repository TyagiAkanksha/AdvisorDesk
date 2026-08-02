"""The real `AgentLLM`: `OpenAICompatibleAgentLLM`, built from `Settings` (PRD §6, v1.5).

Split out from `app.agent.loop` (task-03 brief: "where it lives ... is your call — disclose it")
so `loop.py` — the orchestration seam every `tests/test_agent_loop.py` test exercises directly,
with no HTTP and no provider — never has to import the `openai` SDK at all. This mirrors
`app.rag.embeddings`/`app.rag.synthesis`'s own split of Protocol-plus-fake-friendly modules from
provider-SDK-touching ones, just carried one file further apart.

Talks to NVIDIA NIM's OpenAI-compatible `/v1/chat/completions` endpoint via the `openai` SDK,
mirroring `app.rag.synthesis.OpenAICompatibleChatLLM` exactly (`from_settings`, the same
empty-key boot-safe `"unset"` fallback, `model=settings.chat_model`, no NVIDIA-specific
`extra_body` — the chat-completions path needs none). Unlike `OpenAICompatibleChatLLM.
stream_answer` (token-by-token SSE), `AgentLLM.next_step` returns exactly ONE `LlmStep` per call
(`app.agent.loop`'s own step-at-a-time Protocol) — so each call here issues one non-streaming
`chat.completions.create` request and maps the single response into one step; `run_agent`'s own
call-next_step-in-a-loop behavior is what produces the perceived step-by-step streaming, not the
SDK call itself.

Judgment call (disclosed, task-03 report): the OpenAI wire protocol allows a single turn to
return MULTIPLE `tool_calls` at once (parallel tool calls) even though `next_step` can only
return one `LlmStep` per call. Any extra tool calls from the same turn are queued
(`_pending_tool_calls`) and drained one at a time on later `next_step` calls, without re-querying
the model, before a fresh completion is ever requested again — this keeps the adapter correct if
the pinned model (`meta/llama-3.1-8b-instruct`) ever emits more than one tool call per turn, even
though in practice it rarely does under `tool_choice="auto"`.

Fix round 1 (Opus review of commit e58f007, findings C-2/C-3/I-2):

  - **C-2** — a completion with `content` and no `tool_calls` IS the model's final message (PRD
    §6: "the loop executes tool calls until the model returns a final message"). `next_step` now
    records that fact (`self._finished`) right before returning that final `TextDelta`; the VERY
    NEXT `next_step` call on the SAME instance returns `LlmDone()` immediately, with no further
    provider call, so `run_agent`'s `while True:` actually terminates instead of re-querying a
    conversation that already ended (live-verified: a text-only "What can you do?" answer used
    to trigger 8 unrequested tool calls off the full registry before this fix).
  - **C-3** — `_pending_tool_calls`/`self._finished` are per-EXCHANGE state. Before this fix,
    `app.main` built exactly ONE `OpenAICompatibleAgentLLM` and wired it directly as
    `app.state.agent_llm`, shared by every `/agent/chat` request for the life of the process — a
    still-queued parallel tool call (or a `self._finished=True` left over from a PRIOR request)
    leaked into the NEXT admin's unrelated request, and concurrent requests raced on the same
    mutable list across threadpool workers. Fix: `new_conversation()` below returns a FRESH
    instance sharing this one's `client`/`model` (cheap and thread-safe to share — the `openai`
    SDK's `OpenAI` client wraps its own connection-pooled `httpx.Client`) but starting with an
    empty queue and `self._finished=False`. `app.main` now wires
    `agent_llm_factory=<the one boot-time instance>.new_conversation` into
    `app.factory.create_app`; `app.routes.deps.get_agent_llm` calls that factory FRESH on every
    request, so no per-exchange state can ever survive past the exchange that created it.
  - **I-2** — `tests/test_agent_llm_client.py` (new) is this module's first test coverage at
    all, covering all of the above plus the wire-format request shape, `_to_openai_tools`, the
    `tool_calls` -> `ToolCallStep` mapping (including a malformed-JSON `arguments` string from
    the provider, handled the same way every other provider failure already was — caught by the
    existing `except (..., json.JSONDecodeError)` clause below and turned into
    `AgentLLMFailedError`, never a raw `json.JSONDecodeError` escaping to the caller), the
    `"unset"` boot-safe fallback, and provider errors being logged, never enveloped.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import httpx
from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageFunctionToolCall

from app.agent.loop import LlmDone, LlmStep, TextDelta, ToolCallStep
from app.config import Settings
from app.services.errors import AppError

logger = logging.getLogger(__name__)

__all__ = ["AgentLLMFailedError", "OpenAICompatibleAgentLLM"]


class AgentLLMFailedError(AppError):
    """The real agent LLM provider call failed (PRD §9) — never surfaces provider detail.

    Mirrors `app.rag.synthesis.ChatCompletionFailedError` exactly, for the agent loop's own
    provider seam: raised only from inside the already-streaming `/agent/chat` SSE response body
    (`app.routes.agent_routes`), so — like its sibling — it is never registered against an HTTP
    status in `app.routes.errors`; the route's own SSE generator builds the `error` event around
    it instead.
    """

    code = "agent_llm_failed"


def _to_openai_tools(tool_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adapt `app.mcp.runtime.list_tool_schemas()`'s `{"name","description","inputSchema"}`
    shape into the standard OpenAI `tools=[{"type":"function","function":{...}}]` shape.

    Deliberately done HERE, not in `app.agent.loop` (task-03 brief: "adapt to the OpenAI shape in
    the LLM implementation, not in the loop") — `run_agent` passes `list_tool_schemas()`'s own
    shape straight through to `AgentLLM.next_step`, so a different provider adapter could target
    a different wire shape without touching the loop at all.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["inputSchema"],
            },
        }
        for schema in tool_schemas
    ]


class OpenAICompatibleAgentLLM:
    """The real `AgentLLM`, built from `Settings` (PRD §6, v1.5)."""

    def __init__(self, *, client: OpenAI, model: str) -> None:
        """Store the already-built SDK client plus the model to converse with.

        Args:
            client: an `openai.OpenAI` client pointed at the provider's OpenAI-compatible base
                URL, already carrying the API key.
            model: the chat-completion model name (`Settings.chat_model`).
        """
        self._client = client
        self._model = model
        # Per-EXCHANGE state (fix round 1, findings C-2/C-3) — an instance returned by
        # `new_conversation()` starts with an empty queue and an un-finished turn; see the
        # module docstring's "Fix round 1" section for why this must never be shared across
        # requests.
        self._pending_tool_calls: list[ChatCompletionMessageFunctionToolCall] = []
        self._finished = False

    def new_conversation(self) -> OpenAICompatibleAgentLLM:
        """Return a FRESH `OpenAICompatibleAgentLLM` sharing this instance's `client`/`model`.

        Fix round 1, finding C-3: the per-exchange mutable state (`_pending_tool_calls`,
        `_finished`) must never survive past the request that created it, or leak between
        concurrent requests — but the underlying `client`/`model` are cheap and safe to share
        (the `openai` SDK's `OpenAI` client wraps its own connection-pooled `httpx.Client`).
        `app.main` builds exactly ONE `OpenAICompatibleAgentLLM` at boot and wires
        `agent_llm_factory=<that instance>.new_conversation` into `app.factory.create_app` —
        `app.routes.deps.get_agent_llm` calls it fresh on every `/agent/chat` request.
        """
        return OpenAICompatibleAgentLLM(client=self._client, model=self._model)

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleAgentLLM:
        """Build the real client from `Settings` — the one non-test constructor.

        Mirrors `OpenAICompatibleChatLLM.from_settings` exactly: `nvidia_api_key` falls back to
        the harmless `"unset"` placeholder when empty (dev-mode boot-safety — the `openai` SDK
        raises at *construction* time for a falsy `api_key` with no `OPENAI_API_KEY` env var set
        either, which would crash `app.main`'s module-level wiring on every offline dev boot).
        `timeout=settings.embedding_timeout_seconds`/`max_retries=settings.
        embedding_max_retries` are reused for the same reason `OpenAICompatibleChatLLM` reuses
        them (its own docstring): both budgets bound a single provider call/attempt regardless
        of which OpenAI-compatible endpoint it targets.
        """
        api_key = settings.nvidia_api_key.get_secret_value() or "unset"
        client = OpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(client=client, model=settings.chat_model)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        """Return the model's next step (`AgentLLM` Protocol) via one non-streaming completion.

        Raises:
            AgentLLMFailedError: the provider call failed — any `openai.OpenAIError` (auth, rate
                limit, non-2xx, ...), any `httpx.HTTPError` (a connection reset/timeout), or a
                `json.JSONDecodeError` from parsing a tool call's `arguments` string (mirrors
                `OpenAICompatibleChatLLM.stream_answer`'s exact three-type provider-failure
                family — this also covers a malformed/non-JSON `arguments` string from the
                provider itself, handled the same way, never escaping as a raw
                `json.JSONDecodeError`). The raw provider detail is logged for operators, never
                placed on the exception message.
        """
        try:
            # Fix round 1, finding C-2: the PREVIOUS `next_step` call already returned this
            # exchange's final `TextDelta` (a completion with `content` and no `tool_calls`) —
            # that IS the model's final message (PRD §6). Return `LlmDone()` immediately, with
            # NO provider call, so `run_agent`'s loop actually terminates instead of re-querying
            # a conversation that has already ended.
            if self._finished:
                return LlmDone()

            if self._pending_tool_calls:
                call = self._pending_tool_calls.pop(0)
                return ToolCallStep(call.function.name, json.loads(call.function.arguments))

            response = self._client.chat.completions.create(
                model=self._model,
                messages=cast(Any, messages),
                tools=cast(Any, _to_openai_tools(tool_schemas)),
                tool_choice="auto",
            )
            message = response.choices[0].message

            if message.tool_calls:
                # We only ever define `"type": "function"` tools (`_to_openai_tools`), so a real
                # response should never carry the SDK's other `ChatCompletionMessageToolCall`
                # variant (`...CustomToolCall`) — filtered defensively rather than assumed, so a
                # provider that ever did return one is silently skipped, not a mypy-narrowing
                # crash (`.function` doesn't exist on that variant).
                function_calls = [
                    call
                    for call in message.tool_calls
                    if isinstance(call, ChatCompletionMessageFunctionToolCall)
                ]
                if function_calls:
                    self._pending_tool_calls = function_calls[1:]
                    first = function_calls[0]
                    return ToolCallStep(first.function.name, json.loads(first.function.arguments))

            if message.content:
                # Fix round 1, finding C-2: mark the exchange finished BEFORE returning — the
                # NEXT `next_step` call (this same instance, `run_agent`'s very next loop
                # iteration) returns `LlmDone()` without querying the provider again.
                self._finished = True
                return TextDelta(message.content)

            return LlmDone()
        except (OpenAIError, httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("agent LLM provider call failed: %s", exc)
            raise AgentLLMFailedError("The agent LLM provider call failed.") from exc
