"""Task C (test-author) — `app.agent.anthropic_llm.AnthropicAgentLLM`, the Anthropic adapter for
the agent loop's `AgentLLM` Protocol (brief: .superpowers/sdd/anthropic-haiku/brief.md).

Zero network: a hand-rolled fake `anthropic` client whose `messages.create` records its kwargs and
returns canned responses (`.content` blocks of type text/tool_use, `.stop_reason`).

Pins: tool-schema conversion, request shape (tool_choice auto, effort low, no sampling params,
system split out), OpenAI-shaped history -> Anthropic blocks (tool_use / merged tool_result),
the text -> LlmDone no-requery rule, parallel tool_use queueing, string-encoded arg repair,
error mapping, `new_conversation`, `from_settings`, and the provider-selection factory
`app.agent.llm_factory.build_agent_llm` that `app.main` must use.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from app.agent.anthropic_llm import AnthropicAgentLLM
from app.agent.llm import AgentLLMFailedError, OpenAICompatibleAgentLLM
from app.agent.llm_factory import build_agent_llm
from app.agent.loop import LlmDone, TextDelta, ToolCallStep
from app.config import Settings

_TOOL_SCHEMAS = [
    {
        "name": "search_content",
        "description": "Search CMS content.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    },
    {
        "name": "create_draft",
        "description": "Create a draft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
]

_MESSAGES: list[dict[str, Any]] = [
    {"role": "system", "content": "SYSTEM PROMPT"},
    {"role": "user", "content": "How many published pieces are there?"},
]


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use(id_: str, name: str, input_: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _response(*blocks: SimpleNamespace, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class _FakeMessages:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, *outcomes: Any) -> None:
        self.messages = _FakeMessages(list(outcomes))


def _llm(*outcomes: Any) -> tuple[AnthropicAgentLLM, _FakeClient]:
    client = _FakeClient(*outcomes)
    return AnthropicAgentLLM(client=client, model="claude-haiku-5-5"), client  # type: ignore[arg-type]


def _blocks(content: Any) -> list[dict[str, Any]]:
    """Normalize a message `content` (str or block list) to a block list."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)


# --------------------------------------------------------------------------- request shape


def test_request_shape_tools_choice_effort_and_no_sampling_params() -> None:
    llm, client = _llm(_response(_text("hi")))

    llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    kwargs = client.messages.calls[0]
    assert kwargs["model"] == "claude-haiku-5-5"
    assert isinstance(kwargs["max_tokens"], int) and kwargs["max_tokens"] > 0
    assert kwargs["tool_choice"] == {"type": "auto"}
    assert kwargs["output_config"] == {"effort": "low"}
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in kwargs
    assert kwargs["tools"] == [
        {
            "name": "search_content",
            "description": "Search CMS content.",
            "input_schema": _TOOL_SCHEMAS[0]["inputSchema"],
        },
        {
            "name": "create_draft",
            "description": "Create a draft.",
            "input_schema": _TOOL_SCHEMAS[1]["inputSchema"],
        },
    ]


def test_system_messages_go_to_system_param_not_messages() -> None:
    llm, client = _llm(_response(_text("hi")))

    llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    kwargs = client.messages.calls[0]
    assert "SYSTEM PROMPT" in kwargs["system"]
    assert all(m["role"] != "system" for m in kwargs["messages"])
    assert kwargs["messages"][0]["role"] == "user"
    assert _blocks(kwargs["messages"][0]["content"])[0]["text"] == _MESSAGES[1]["content"]


def test_history_converts_tool_calls_and_merges_consecutive_tool_results() -> None:
    history: list[dict[str, Any]] = [
        *_MESSAGES,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_content", "arguments": json.dumps({"q": "ira"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "3 results"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "search_content", "arguments": json.dumps({"q": "401k"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "1 result"},
        {"role": "tool", "tool_call_id": "call_3", "content": "refused"},
    ]
    llm, client = _llm(_response(_text("done")))

    llm.next_step(history, _TOOL_SCHEMAS)

    sent = client.messages.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user", "assistant", "user"]
    assert _blocks(sent[1]["content"]) == [
        {"type": "tool_use", "id": "call_1", "name": "search_content", "input": {"q": "ira"}}
    ]
    assert _blocks(sent[2]["content"]) == [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "3 results"}
    ]
    assert _blocks(sent[3]["content"]) == [
        {"type": "tool_use", "id": "call_2", "name": "search_content", "input": {"q": "401k"}}
    ]
    # Two consecutive `tool` messages collapse into ONE user message.
    assert _blocks(sent[4]["content"]) == [
        {"type": "tool_result", "tool_use_id": "call_2", "content": "1 result"},
        {"type": "tool_result", "tool_use_id": "call_3", "content": "refused"},
    ]


def test_assistant_text_message_is_passed_as_assistant_text() -> None:
    history = [*_MESSAGES, {"role": "assistant", "content": "earlier answer"}]
    llm, client = _llm(_response(_text("ok")))

    llm.next_step(history, _TOOL_SCHEMAS)

    sent = client.messages.calls[0]["messages"]
    assert sent[-1]["role"] == "assistant"
    assert _blocks(sent[-1]["content"]) == [{"type": "text", "text": "earlier answer"}]


# --------------------------------------------------------------------------- response mapping


def test_text_only_response_returns_textdelta_then_done_without_second_call() -> None:
    llm, client = _llm(_response(_text("There are 12.")))

    first = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    second = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert first == TextDelta("There are 12.")
    assert isinstance(second, LlmDone)
    assert len(client.messages.calls) == 1


def test_single_tool_use_returns_tool_call_step_with_dict_arguments() -> None:
    llm, _ = _llm(
        _response(_tool_use("tu_1", "search_content", {"q": "roth"}), stop_reason="tool_use")
    )

    step = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.name == "search_content"
    assert step.arguments == {"q": "roth"}


def test_parallel_tool_use_blocks_are_queued_and_drained_without_requery() -> None:
    llm, client = _llm(
        _response(
            _text("Checking both."),
            _tool_use("tu_1", "search_content", {"q": "a"}),
            _tool_use("tu_2", "search_content", {"q": "b"}),
            stop_reason="tool_use",
        )
    )

    first = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    second = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(first, ToolCallStep) and first.arguments == {"q": "a"}
    assert isinstance(second, ToolCallStep) and second.arguments == {"q": "b"}
    assert len(client.messages.calls) == 1


def test_string_encoded_array_argument_is_repaired() -> None:
    llm, _ = _llm(
        _response(
            _tool_use("tu_1", "create_draft", {"title": "T", "tags": "['retirement']"}),
            stop_reason="tool_use",
        )
    )

    step = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(step, ToolCallStep)
    assert step.arguments == {"title": "T", "tags": ["retirement"]}


def test_queued_tool_call_also_gets_argument_repair() -> None:
    llm, _ = _llm(
        _response(
            _tool_use("tu_1", "search_content", {"q": "x"}),
            _tool_use("tu_2", "create_draft", {"title": "T", "tags": '["a"]'}),
            stop_reason="tool_use",
        )
    )

    llm.next_step(_MESSAGES, _TOOL_SCHEMAS)
    second = llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert isinstance(second, ToolCallStep)
    assert second.arguments["tags"] == ["a"]


# --------------------------------------------------------------------------- errors


def _api_error() -> anthropic.APIError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.example/v1"))


def test_anthropic_api_error_becomes_agent_llm_failed_error() -> None:
    llm, _ = _llm(_api_error())

    with pytest.raises(AgentLLMFailedError) as exc_info:
        llm.next_step(_MESSAGES, _TOOL_SCHEMAS)

    assert "x.example" not in str(exc_info.value)


def test_httpx_error_becomes_agent_llm_failed_error() -> None:
    llm, _ = _llm(httpx.ReadTimeout("boom"))

    with pytest.raises(AgentLLMFailedError):
        llm.next_step(_MESSAGES, _TOOL_SCHEMAS)


def test_refusal_stop_reason_becomes_agent_llm_failed_error() -> None:
    llm, _ = _llm(_response(_text("I can't help"), stop_reason="refusal"))

    with pytest.raises(AgentLLMFailedError):
        llm.next_step(_MESSAGES, _TOOL_SCHEMAS)


# --------------------------------------------------------------------------- lifecycle / config


def test_new_conversation_is_fresh_and_shares_client_and_model() -> None:
    llm, client = _llm(
        _response(
            _tool_use("tu_1", "search_content", {"q": "a"}),
            _tool_use("tu_2", "search_content", {"q": "b"}),
            stop_reason="tool_use",
        ),
        _response(_text("fresh")),
    )
    llm.next_step(_MESSAGES, _TOOL_SCHEMAS)  # leaves one queued call on `llm`

    fresh = llm.new_conversation()

    assert isinstance(fresh, AnthropicAgentLLM)
    assert fresh is not llm
    assert fresh._client is llm._client
    assert fresh._model == llm._model
    assert fresh.next_step(_MESSAGES, _TOOL_SCHEMAS) == TextDelta("fresh")
    assert len(client.messages.calls) == 2


def test_from_settings_uses_anthropic_key_and_chat_model() -> None:
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        chat_model="claude-haiku-5-5",
    )

    llm = AnthropicAgentLLM.from_settings(settings)

    assert llm._client.api_key == "sk-ant-test"
    assert llm._model == "claude-haiku-5-5"


def test_from_settings_falls_back_to_unset_when_key_is_empty() -> None:
    llm = AnthropicAgentLLM.from_settings(Settings(llm_provider="anthropic", anthropic_api_key=""))

    assert llm._client.api_key == "unset"


# --------------------------------------------------------------------------- wiring


def test_build_agent_llm_selects_anthropic_for_anthropic_provider() -> None:
    settings = Settings(llm_provider="anthropic", anthropic_api_key="sk-ant-test")

    assert isinstance(build_agent_llm(settings), AnthropicAgentLLM)


@pytest.mark.parametrize("provider", ["openai", "nvidia"])
def test_build_agent_llm_keeps_openai_compatible_for_other_providers(provider: str) -> None:
    settings = Settings(llm_provider=provider, openai_api_key="sk-x", nvidia_api_key="nv-x")  # type: ignore[arg-type]

    assert isinstance(build_agent_llm(settings), OpenAICompatibleAgentLLM)


def test_main_wires_agent_llm_through_build_agent_llm() -> None:
    main_source = (Path(__file__).parent.parent / "app" / "main.py").read_text()

    assert "build_agent_llm(settings)" in main_source
    assert "OpenAICompatibleAgentLLM.from_settings(settings)" not in main_source
