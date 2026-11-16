"""`AnthropicAgentLLM`: the agent loop's `AgentLLM` over the official `anthropic` SDK.

Converts `run_agent`'s OpenAI-shaped history and MCP-shaped tool schemas into Anthropic
Messages API shapes. Per-exchange state (`_pending`, `_finished`) mirrors
`OpenAICompatibleAgentLLM`; `new_conversation()` returns a fresh instance sharing client/model.
Haiku 5.5 rejects non-default sampling params, so none are sent; effort is Settings.llm_effort.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import anthropic
import httpx

from app.agent.llm import AgentLLMFailedError, _repair_string_encoded_arguments
from app.agent.loop import LlmDone, LlmStep, TextDelta, ToolCallStep
from app.config import Settings

logger = logging.getLogger(__name__)

__all__ = ["AnthropicAgentLLM"]


def _to_anthropic_tools(tool_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "input_schema": s["inputSchema"],
        }
        for s in tool_schemas
    ]


def _assistant_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if message.get("content"):
        blocks.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls") or []:
        function = call["function"]
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": function["name"],
                "input": json.loads(function["arguments"] or "{}"),
            }
        )
    return blocks


def _to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI-shaped `messages` into (`system` text, Anthropic `messages`)."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            system_parts.append(str(message["content"]))
        elif role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": message["tool_call_id"],
                "content": str(message["content"]),
            }
            last = converted[-1] if converted else None
            if last and last["role"] == "user" and isinstance(last["content"], list):
                if all(b.get("type") == "tool_result" for b in last["content"]):
                    last["content"].append(result)
                    continue
            converted.append({"role": "user", "content": [result]})
        elif role == "assistant":
            converted.append({"role": "assistant", "content": _assistant_blocks(message)})
        else:
            converted.append({"role": "user", "content": message["content"]})
    return "\n\n".join(system_parts), converted


class AnthropicAgentLLM:
    """The Anthropic `AgentLLM`, built from `Settings`."""

    def __init__(
        self,
        *,
        client: anthropic.Anthropic,
        model: str,
        max_tokens: int = 2048,
        effort: str = "low",
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._pending: list[Any] = []
        self._finished = False

    def new_conversation(self) -> AnthropicAgentLLM:
        """Fresh per-exchange instance sharing this one's client and model."""
        return AnthropicAgentLLM(
            client=self._client,
            model=self._model,
            max_tokens=self._max_tokens,
            effort=self._effort,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> AnthropicAgentLLM:
        """Build from `Settings`; an empty key becomes the boot-safe `"unset"` placeholder."""
        api_key = settings.llm_api_key.get_secret_value() or "unset"
        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(
            client=client,
            model=settings.chat_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
        )

    def _tool_step(self, block: Any, tool_schemas: list[dict[str, Any]]) -> ToolCallStep:
        arguments = _repair_string_encoded_arguments(dict(block.input), block.name, tool_schemas)
        return ToolCallStep(block.name, arguments)

    def next_step(
        self, messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]]
    ) -> LlmStep:
        """Return the model's next step (`AgentLLM` Protocol).

        Raises:
            AgentLLMFailedError: provider failure or a `refusal` stop; detail is logged only.
        """
        if self._finished:
            return LlmDone()
        if self._pending:
            return self._tool_step(self._pending.pop(0), tool_schemas)
        system, converted = _to_anthropic_messages(messages)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=cast(Any, converted),
                tools=cast(Any, _to_anthropic_tools(tool_schemas)),
                tool_choice={"type": "auto"},
                output_config=cast(Any, {"effort": self._effort}),
            )
        except (anthropic.APIError, httpx.HTTPError) as exc:
            logger.warning("agent LLM provider call failed: %s", exc)
            raise AgentLLMFailedError("The agent LLM provider call failed.") from exc
        if response.stop_reason == "refusal":
            logger.warning("agent LLM provider refused the request")
            raise AgentLLMFailedError("The agent LLM provider call failed.")
        if response.stop_reason == "max_tokens":
            logger.warning("agent LLM reply truncated (stop_reason=max_tokens)")
            raise AgentLLMFailedError("The agent LLM provider call failed.")
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if tool_uses:
            self._pending = tool_uses[1:]
            return self._tool_step(tool_uses[0], tool_schemas)
        text = "".join(b.text for b in response.content if b.type == "text")
        if text:
            self._finished = True
            return TextDelta(text)
        return LlmDone()
